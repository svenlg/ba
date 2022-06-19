# Import
import torch
import numpy as np

# [PAD]  Padding token 512 tokens per seqences                          0   (0)
# [UNK]  Used when a word is unknown to Bert                          101 (100)
# [CLS]  Appears at the start of every sequence                       102 (101)
# [SEP]  Indicates a seperator - between and end of sequences token   103 (102)
# [MASK] Used when masking tokens, masked language modelling (MLM)    104 (103)


# Returns a dict with masked input_ids an labels
def get_tensors(ocn):

    # load the tokenized representaion of the laws
    input_ids = torch.from_numpy(np.load(ocn))
    att_mask = torch.ones(input_ids.size())

    chunksize = 512

    # split into chunks so the model can prosses the full law
    input_id_chunks = input_ids.split(chunksize-2)
    att_mask_chunks = att_mask.split(chunksize-2)


    input_id_chunks = list(input_id_chunks)
    att_mask_chunks = list(att_mask_chunks)
    labels = [0]*len(input_id_chunks)

    for i in range(len(input_id_chunks)):

        # copy the input_ids so we get labels
        label = input_id_chunks[i].clone()
        # create random array of floats in equal dimension to input_ids
        rand = torch.rand(label.shape)
        # where the random array is less than 0.15, we set true
        mask_arr = (rand < 0.15)
        # change all true values in the mask to [MASK] tokens (104)
        input_id_chunks[i][mask_arr] = 104

        # add the [CLS] = 102 and [SEP] = 103 tokens
        input_id_chunks[i] = torch.cat([
            torch.Tensor([102]), input_id_chunks[i], torch.Tensor([103])
        ])
        att_mask_chunks[i] = torch.cat([
            torch.Tensor([1]), att_mask_chunks[i], torch.Tensor([1])
        ])
        labels[i] = torch.cat([
            torch.Tensor([102]), label ,torch.Tensor([103])
        ])

        # get required padding length
        pad_len = chunksize - input_id_chunks[i].shape[0]

        # check if tensor length satisfies required chunk size
        if pad_len > 0:

            # if padding length is more than 0, we must add padding
            input_id_chunks[i] = torch.cat([
                input_id_chunks[i], torch.Tensor([0] * pad_len)
            ])
            att_mask_chunks[i] = torch.cat([
                att_mask_chunks[i], torch.Tensor([0] * pad_len)
            ])
            labels[i] = torch.cat([
                labels[i], torch.Tensor([0] * pad_len)
            ])

    # list to tensors
    input_ids = torch.stack(input_id_chunks)
    attentions_mask = torch.stack(att_mask_chunks)
    labels = torch.stack(labels)

    # input_dict so the model can prosses the data
    input_dict = {
        'input_ids': input_ids.long(),
        'attention_mask': attentions_mask.int(),
        'labels': labels.long()
    }

    return input_dict


# Get the old change new Law as list of tripples
def get_old_change_new(fname, law):

    law = str(law)
    fname = fname + law + '/'
    changes = np.loadtxt(fname + 'changes.txt', dtype=str, encoding='utf-8')

    ten_law = []

    if changes.shape == ():
        change = str(changes)
        old = get_tensors(fname + change + '/old.npy')
        ten_law.append(old)
        cha = get_tensors(fname + change + '/change.npy')
        ten_law.append(cha)
        new = get_tensors(fname + change + '/new.npy')
        ten_law.append(new)
        return ten_law

    for change in changes:
        change = str(change)

        if law == 'KWG' and change == 'Nr7_2020-12-29':
            continue

        old = get_tensors(fname + change + '/old.npy')
        ten_law.append(old)
        cha = get_tensors(fname + change + '/change.npy')
        ten_law.append(cha)
        new = get_tensors(fname + change + '/new.npy')
        ten_law.append(new)
   
    return ten_law


# test tries
def get_laws(split=1, use_set=True):

    assert 0 <= split <= 1

    if use_set:
        #fname = '/scratch/sgutjahr/Data_Tokenized/'
        fname = '/scratch/sgutjahr/Data_Token/'
    else:
        #fname = '../Data_Tokenized/'
        fname = '../Data_Token/' 

    laws = np.loadtxt(fname + 'done_with.txt', dtype=str, encoding='ISO-8859-1')
    big = []
    np.random.shuffle(laws)
    num_data = int(split*len(laws))

    for i in range(num_data):
        big.append(get_old_change_new(fname, laws[i]))

    flat = []
    for li in big:
        for di in li:
            flat.append(di)

    ret = []
    for part in flat:
        input_ids = part['input_ids']
        attention_mask = part['attention_mask']
        labels = part['labels']

        for i in range(input_ids.shape[0]):
            new = dict(
                input_ids = input_ids[i],
                attention_mask = attention_mask[i],
                labels = labels[i]
            )
            ret.append(new)

    print(f'{num_data} out of {len(laws)} will be used for training.')
    print(f'There are {len(flat)} ocn and {len(ret)} batch lines.\n')

    return ret
