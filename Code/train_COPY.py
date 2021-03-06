# Imports
import argparse
import os
import time
import numpy as np
from tqdm import tqdm

import torch.multiprocessing as mp
import torch
from torch import optim
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler
from torch.utils.data import DataLoader

from lawsCOPY import get_laws_for_Copy, DatasetForCOPY
from encoder_decoder import EncoderDecoder
from evaluate import evaluate


def train(rank, args):

    # Settings
    torch.manual_seed(args.seed)

    dist.init_process_group(backend='nccl',
                            world_size=args.world_size,
                            rank=rank)

    # Getting the data train and test and split the trainings data into train and val sets
    path = '/scratch/sgutjahr/Data_Token_Copy/'
    model_path = '/scratch/sgutjahr/log/ddp500_BERT_MLM_best.pt'

    data_train = get_laws_for_Copy(path, 'train')
    data_val = get_laws_for_Copy(path, 'val')
    device = torch.device(f'cuda:{rank}')
    encoder_decoder = EncoderDecoder(model_path, device, hidden_size=args.hidden_size)

    # Wrap the model
    encoder_decoder = DDP(encoder_decoder, device_ids=[rank], find_unused_parameters=True)

    # define optimizer
    optimizer = optim.Adam(encoder_decoder.parameters(), lr=args.lr)
    loss_function = torch.nn.NLLLoss(ignore_index=0)

    train_dataset = DatasetForCOPY(data_train,device)
    val_dataset = DatasetForCOPY(data_val,device)

    train_sampler = DistributedSampler(train_dataset,
                                       num_replicas=args.world_size,
                                       rank=rank)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size,
                              shuffle=False,
                              num_workers=0,
                              sampler=train_sampler)

    val_sampler = DistributedSampler(val_dataset,
                                     num_replicas=args.world_size,
                                     rank=rank)

    val_loader = DataLoader(val_dataset, batch_size=args.batch_size,
                            shuffle=False,
                            num_workers=0,
                            sampler=val_sampler)

    loss_train = []
    loss_val = []
    stat_acc = []

    print(f'Start finetuning model')
    best_round = 0
    INF = 10e9
    cur_low_val_eval = INF

    for epoch in range(1,args.epochs+1):

        encoder_decoder.train()
        train_sampler.set_epoch(epoch)
        val_sampler.set_epoch(epoch)
        # reset statistics trackers
        t = time.time()
        train_loss_cum = 0
        num_samples_epoch = 0

        pbar = tqdm(train_loader, desc=f'Training on GPU{rank} [{epoch}/{args.epochs}]', leave=True)

        for input_,change_,target_ in pbar:

            # input_,change_,target_  all ready at the device
            batch_size = input_['input_ids'].shape[0]

            optimizer.zero_grad()
            # output_log_probs.shape = (b, max_length, voc_size)
            # output_seqs.shape: (b, max_length, 1)
            output_log_probs, output_seqs = encoder_decoder(input_,change_,target_,teacher_forcing=args.schedule[epoch-1])

            # flattened_outputs.shape = (b * max_length, voc_size)
            flattened_outputs = output_log_probs.view(batch_size * args.max_length, -1)
            # target_.contiguous().view(-1).shape: (b * max_length)
            loss = loss_function(flattened_outputs, target_.contiguous().view(-1))
            loss.backward()
            optimizer.step()

            # keep track of train stats
            num_samples_epoch += batch_size
            train_loss_cum += loss * batch_size

            pbar.set_postfix({'loss': f'{loss.item():.2f}'})
            loss_train.append(loss.item())


        avg_train_loss = train_loss_cum / num_samples_epoch

        val_loss, acc = evaluate(encoder_decoder, val_loader)
        loss_val.append(val_loss)
        stat_acc.append(acc)
        epoch_duration = time.time() - t

        # print some infos
        print(f'Epoch {epoch} | Rank {rank} | Duration {epoch_duration:.2f} sec\n'
              f'Avgtrain loss: {avg_train_loss:.4f}\n'
              f'Validation loss: {val_loss:.4f}\n'
              f'accuracy_score:  {acc:.4f}\n', flush=True)

        if cur_low_val_eval > val_loss and epoch > 4:
            cur_low_val_eval = val_loss
            best_round = epoch
            save_path = f'/scratch/sgutjahr/log/{args.model_name}_COPY_{rank}.pt'
            torch.save({'epoch': epoch,
                        'model_state_dict': encoder_decoder.module.state_dict(),
                        'loss': cur_low_val_eval}, save_path)

        if epoch % 2 == 0:
            np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_epoch_train_{rank}.npy', np.array(loss_train))
            np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_epoch_val_{rank}.npy', np.array(loss_val))
            np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_epoch_acc_{rank}.npy', np.array(stat_acc))


    print(f'Lowest validation loss: {cur_low_val_eval:.4f} in Round {best_round}')
    np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_train_{rank}.npy', np.array(loss_train))
    np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_val_{rank}.npy', np.array(loss_val))
    np.save(f'/scratch/sgutjahr/log/{args.model_name}_COPY_acc_{rank}.npy', np.array(stat_acc))
    dist.destroy_process_group()
    
    return


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Parse training parameters')

    parser.add_argument('model_name', type=str,
                        help='the name of a subdirectory of ./model/ that '
                             'contains encoder and decoder model files')

    parser.add_argument('-e', '--epochs', type=int, default=50,
                        help='the number of epochs to train')

    parser.add_argument('-bs', '--batch_size', type=int, default=3,
                        help='number of examples in a batch')

    parser.add_argument('-v', '--val_size', type=float, default=0.15,
                        help='fraction of data to use for validation')

    parser.add_argument('--lr', type=float, default=5e-5,
                        help='Learning rate.')

    parser.add_argument('--hidden_size', type=int, default=185,
                        help='The hidden size of the GRU unit')

    parser.add_argument('--max_length', type=int, default=512,
                        help='Sequences will be padded or truncated to this size.')

    parser.add_argument('--seed', type=int, default=42,
                        help='Seed for spliting and loader.')

    args = parser.parse_args()

    torch.backends.cudnn.benchmark = True

    args.world_size = torch.cuda.device_count()
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '8888'

    took = time.time()
    print('',flush=True)
    print(f'training of {args.model_name}', flush=True)
    print(f'More information:\n'
          f'lr = {args.lr} | hidden_size = {args.hidden_size} | max_length = {args.max_length} | batch_size = {args.batch_size}\n', flush=True)
    
    args.schedule = np.arange(1.0, 0.0, -1.0/args.epochs)
    #Train the Model
    mp.spawn(train, nprocs=args.world_size, args=(args,), join=True)

    print(f'Done')
    duration = time.time() - took
    print(f'Took: {duration/60:.4f} min\n')

