import torch.nn as nn
from transformers import BertForMaskedLM
from torch.utils.data import Dataset
from numpy.random import randint

class LawNetMLM(nn.Module):

    def __init__(self, checkpoint):
        super(LawNetMLM, self).__init__()
        self.model = BertForMaskedLM.from_pretrained(checkpoint)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        #Extract outputs from the body
        outputs = self.model(input_ids=input_ids,
                             attention_mask=attention_mask,
                             labels=labels)
        return outputs


# Data set for the MLM Task
class LawDatasetForMLM(Dataset):

    def __init__(self, data, size):
        self.data = data
        self.len = size
        self.mod = len(self.data)
        self.epoch = 0
        self.rand = 0

    def __len__(self):
        self.epoch += 1
        self.rand = randint(12345)
        return self.len

    def __getitem__(self, idx):
        idx = (idx + self.rand + self.len*self.epoch) % self.mod
        return self.data[idx]

