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

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import paddle
import paddle.nn as nn
from paddle.optimizer.lr import LambdaDecay
from predict_generation import Predictor, batchfy_text
from rouge import Rouge

from paddlenlp.metrics import BLEU
from paddlenlp.trainer import Trainer


def save_infer_result(trainer, dev_ds, k=100, src_length=256, tgt_length=512):
    all_instructions = []
    all_answers = []
    all_output = []

    # top k instruction from dev_ds
    for i, ds in enumerate(dev_ds.data):
        if i == k:
            break
        all_instructions.append(ds["instruction"])
        all_answers.append(ds["output"])
    batch_texts = batchfy_text(all_instructions, trainer.args.per_device_eval_batch_size)
    predictor = Predictor(
        tokenizer=trainer.tokenizer, model=trainer.model, src_length=src_length, tgt_length=tgt_length
    )

    # infer results
    for bs, texts in enumerate(batch_texts):
        outputs = predictor.predict(texts)
        for i, (text, result) in enumerate(zip(texts, outputs["result"])):
            out = {
                "instruction": text,
                "answer": all_answers[bs * trainer.args.per_device_eval_batch_size + i],
                "output": result,
            }
            all_output.append(out)

    # save results
    if trainer.args.tensor_parallel_rank == 0:
        with open(os.path.join(trainer.args.output_dir, "infer_result.json"), "w") as f:
            for out in all_output:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")


class LlamaTrainer(Trainer):
    def __init__(self, do_generation: bool, **kwargs):
        super().__init__(**kwargs)
        self.do_generation = do_generation

    def prediction_step(
        self,
        model: nn.Layer,
        inputs: Dict[str, Union[paddle.Tensor, Any]],
        prediction_loss_only: bool,
        ignore_keys: Optional[List[str]] = None,
    ) -> Tuple[Optional[paddle.Tensor], Optional[paddle.Tensor], Optional[paddle.Tensor]]:

        if prediction_loss_only:
            return super().prediction_step(model, inputs, prediction_loss_only, ignore_keys)
        elif not self.do_generation:
            loss, logits, labels = super().prediction_step(model, inputs, prediction_loss_only, ignore_keys)
            # argmax here to avoid gather all logits, which is too memory-consuming.
            # keepdim in order to maintain the same shape as logits
            return (loss, logits[..., :-1, :].argmax(axis=-1, keepdim=True), labels[..., 1:])
        model.eval()

        preds = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_length=50,
            min_length=0,
            use_cache=True,
            temperature=1.0,
            top_k=1,
            top_p=1.0,
            repetition_penalty=1.0,
            decode_strategy="sampling",
        )[0]
        all_labels = []
        for label in inputs["labels"].numpy():
            label = [x for x in label[label != self.tokenizer.pad_token_id]]
            all_labels.append(label)
        max_label_length = max([len(x) for x in all_labels])
        for index, labels in enumerate(all_labels):
            all_labels[index] = labels + [-100] * (max_label_length - len(labels))

        return (None, paddle.to_tensor(preds), paddle.to_tensor(all_labels))

    def create_scheduler(self, num_training_steps: int):
        num_warmup_steps = (
            self.args.warmup_steps if self.args.warmup_steps > 0 else self.args.warmup_ratio * num_training_steps
        )

        def lr_lambda(current_step: int):
            if current_step < num_warmup_steps:
                return float(current_step) / float(max(1, num_warmup_steps))
            else:
                decay_step_ratio = (current_step - num_warmup_steps) / (num_training_steps - num_warmup_steps)
                return 1.0 - (1.0 - self.args.lr_decay_ratio) * decay_step_ratio

        if self.lr_scheduler is None:
            self.lr_scheduler = LambdaDecay(self.args.learning_rate, lr_lambda, last_epoch=-1)
        return self.lr_scheduler

    def log(self, logs: Dict[str, float], **kwargs) -> None:
        if "loss" in logs:
            logs["ppl"] = np.exp(logs["loss"])
        if "eval_loss" in logs:
            logs["eval_ppl"] = np.exp(logs["eval_loss"])

        super(LlamaTrainer, self).log(logs, **kwargs)


def compute_metrics(preds, targets):
    assert len(preds) == len(targets), (
        "The length of pred_responses should be equal to the length of "
        "target_responses. But received {} and {}.".format(len(preds), len(targets))
    )
    rouge = Rouge()
    bleu4 = BLEU(n_size=4)
    scores = []
    for pred, target in zip(preds, targets):
        try:
            score = rouge.get_scores(" ".join(pred), " ".join(target))
            scores.append([score[0]["rouge-1"]["f"], score[0]["rouge-2"]["f"], score[0]["rouge-l"]["f"]])
        except ValueError:
            scores.append([0, 0, 0])
        bleu4.add_inst(pred, [target])
    rouge1 = np.mean([i[0] for i in scores])
    rouge2 = np.mean([i[1] for i in scores])
    rougel = np.mean([i[2] for i in scores])

    rouge1 = round(rouge1, 4)
    rouge2 = round(rouge2, 4)
    rougel = round(rougel, 4)
    bleu4 = round(bleu4.score(), 4)
    return dict(
        rouge1=rouge1,
        rouge2=rouge2,
        rougel=rougel,
        bleu4=bleu4,
    )
