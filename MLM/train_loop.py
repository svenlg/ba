import numpy as np
import torch
import time
from eval import evaluate


# Trainigs Loop for BertMLM Task
def train_loop(model, train_loader, val_loader, optim, device, mask, checkpoint, show=1, save=40, epochs=200, name='try'):

    loss_train = np.empty((epochs,))
    loss_split = np.empty((epochs,4))
    loss_val = np.empty((epochs,3))

    print(f'Start finetuning model')
    best_round = 0
    INF = 10e9
    cur_low_val_eval = INF

    for epoch in range(1,epochs+1):
        # reset statistics trackers
        train_loss_cum = 0.0
        num_samples_epoch = 0
        t = time.time()
        split = torch.empty((4,)).to(device)

        # Go once through the training dataset (-> epoch)
        for batch in train_loader:
            # get batches 
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['labels'].to(device)

            # zero grads and put model into train mode            
            optim.zero_grad()
            model.train()

            # trainings step
            outputs = model(input_ids, attention_mask=attention_mask, labels=labels)

            # loss
            loss = outputs[0].mean()

            # backward pass and gradient step
            loss.backward()
            optim.step()

            # keep track of train stats
            num_samples_batch = input_ids.shape[0]
            num_samples_epoch += num_samples_batch
            split += outputs[0] * num_samples_batch
            train_loss_cum += loss * num_samples_batch

        # average the accumulated statistics
        avg_train_loss = train_loss_cum / num_samples_epoch
        avg_gpu_loss = split.to('cpu') / num_samples_epoch
        loss_train[epoch-1] = avg_train_loss.item()
        loss_split[epoch-1] = avg_gpu_loss.detach().numpy()

        # val_loss = val_loss, acc, f1
        val_loss, acc, f1 = evaluate(model, val_loader, device, mask)
        loss_val[epoch-1] = [val_loss, acc, f1]
        epoch_duration = time.time() - t

        # print some infos
        if epoch % show == 0:
            print(f'Epoch {epoch} | Duration {epoch_duration:.2f} sec')
            print(f'Train loss:      {avg_train_loss:.4f}')
            print(f'Validation loss: {val_loss:.4f}')
            print(f'accuracy_score:  {acc:.4f}')
            print(f'f1_score:        {f1:.4f}\n')

        # save checkpoint of model
        if epoch % save == 0 and epoch > 25:
            save_path = f'/scratch/sgutjahr/log/{name}_BERT_MLM_epoch_{epoch}.pt'
            torch.save({'model_state_dict': model.module.state_dict(),
                        'loss': val_loss}, save_path)
            np.save(f'/scratch/sgutjahr/log/{name}_loss_train.npy', loss_train)
            np.save(f'/scratch/sgutjahr/log/{name}_loss_val.npy', loss_val)
            np.save(f'/scratch/sgutjahr/log/{name}_loss_split.npy', loss_split)
            print(f'Saved model and loss stats in epoch {epoch}\n')

        if cur_low_val_eval > val_loss and epoch > 10:
            cur_low_val_eval = val_loss
            best_round = epoch
            save_path = f'/scratch/sgutjahr/log/{name}_BERT_MLM_best.pt'
            torch.save({'checkpoint': checkpoint,
                        'epoch': epoch,
                        'model_state_dict': model.module.state_dict(),
                        'loss': cur_low_val_eval,
                        'accuracy': acc,
                        'f1': f1}, save_path)


    print(f'Lowest validation loss: {cur_low_val_eval:.4f} in Round {best_round}')
    np.save(f'/scratch/sgutjahr/log/{name}_loss_train.npy', loss_train)
    np.save(f'/scratch/sgutjahr/log/{name}_loss_val.npy', loss_val)
    np.save(f'/scratch/sgutjahr/log/{name}_loss_split.npy', loss_split)
    print('')

