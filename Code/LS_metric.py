#Imports
import numpy as np
import Levenshtein

import torch
from torch.utils.data import DataLoader
from encoder_decoder import EncoderDecoder
from lawsCOPY import get_laws_for_Copy, DatasetForCOPY

from transformers import AutoTokenizer

pre = '/scratch/sgutjahr'
model_path = pre + '/log/ddp500_BERT_MLM_best.pt'
path = pre + '/Data_Token_Copy/'
checkpoint_to = 'dbmdz/bert-base-german-cased'
checkpoint_mo = pre + '/log/FT_COPY_best.pt'
tokenizer = AutoTokenizer.from_pretrained(checkpoint_to)
use_cuda = torch.cuda.is_available()
device = torch.device('cuda:0' if use_cuda else 'cpu')

hidden_size = 185

data = get_laws_for_Copy(path)

checkpoint = torch.load(checkpoint_mo, map_location=(device))
COPY = EncoderDecoder(model_path, device, hidden_size=hidden_size)
COPY.load_state_dict(checkpoint['model_state_dict'])

dataset = DatasetForCOPY(data, device)
loader = DataLoader(dataset, batch_size=1, shuffle=False)

stats = []
tokens = []
print(f'\nLETS GO')


for i, (input_,change_,target_) in enumerate(loader):

    output_log_probs, output_seqs = COPY(input_,change_)

    target_ = target_[0]
    output_seqs = output_seqs.squeeze(-1)[0]
    tar_seq = tokenizer.decode(target_)
    out_seq = tokenizer.decode(output_seqs)

    want_ = ''
    for j, let in enumerate(tar_seq):
        if let == '[' and tar_seq[j:j+5] == '[SEP]':
            #exclude the [CLS] and the [SEP token]
            want_ = tar_seq[6:j-1]
            break

    is_ = ''
    for k, let in enumerate(out_seq):
        if let == '[' and out_seq[k:k+5] == '[SEP]':
            #exclude the [CLS] and the [SEP token]
            is_ = out_seq[6:k-1]
            break

    LD = Levenshtein.distance(want_, is_)
    LD_rel = LD / len(want_)

    stats.append([i, LD, LD_rel])
    to = np.vstack((target_.cpu().numpy(),output_seqs.cpu().numpy()))
    tokens.append(to)
    print(f'Round {i+1} | LD={LD} | LD_rel={LD_rel:.4f}')


save_stats = pre + '/log/levenshtein_stats.npy'
save_token = pre + '/log/levenshtein_token.npy'
stats = np.array(stats)
tokens = np.array(tokens)
np.save(save_stats, stats)
np.save(save_token, tokens)
print('done')

