# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os

import paddle
import paddle.nn.functional as F
from paddlenlp.experimental import FasterErnieModel, FasterErnieForSequenceClassification, to_tensor

# yapf: disable
parser = argparse.ArgumentParser()
parser.add_argument("--save_path", type=str, default="checkpoint/model_900", help="The path to model parameters to be loaded.")
parser.add_argument("--max_seq_length", type=int, default=128, help="The maximum total input sequence length after tokenization. "
    "Sequences longer than this will be truncated, sequences shorter will be padded.")
parser.add_argument("--batch_size", type=int, default=32, help="Batch size per GPU/CPU for training.")
parser.add_argument('--device', choices=['cpu', 'gpu', 'xpu'], default="gpu", help="Select which device to train model, defaults to gpu.")
args = parser.parse_args()
# yapf: enable


def predict(model, data, label_map, batch_size=1):
    # Seperates data into some batches.
    batches = [
        data[idx:idx + batch_size] for idx in range(0, len(data), batch_size)
    ]

    results = []
    model.eval()
    for texts in batches:
        texts = to_tensor(texts)
        logits, predictions = model(texts)
        probs = F.softmax(logits, axis=1)
        idx = paddle.argmax(probs, axis=1).numpy()
        idx = idx.tolist()
        labels = [label_map[i] for i in idx]
        results.extend(labels)
    return results


if __name__ == "__main__":
    paddle.set_device(args.device)

    data = [
        '这个宾馆比较陈旧了，特价的房间也很一般。总体来说一般',
        '怀着十分激动的心情放映，可是看着看着发现，在放映完毕后，出现一集米老鼠的动画片',
        '作为老的四星酒店，房间依然很整洁，相当不错。机场接机服务很好，可以在车上办理入住手续，节省时间。',
    ]
    label_map = {0: 'negative', 1: 'positive'}

    model = FasterErnieForSequenceClassification.from_pretrained(args.save_path)
    results = predict(model, data, label_map, batch_size=args.batch_size)
    for idx, text in enumerate(data):
        print('Data: {} \t Lable: {}'.format(text, results[idx]))
