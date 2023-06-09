# Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
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

import requests

url = "http://0.0.0.0:8189/taskflow/cls"
headers = {"Content-Type": "application/json"}

if __name__ == "__main__":
    texts = ["黑苦荞茶的功效与作用及食用方法", "交界痣会凸起吗", "检查是否能怀孕挂什么科", "鱼油怎么吃咬破吃还是直接咽下去", "幼儿挑食的生理原因是"]
    data = {"data": {"text": texts}}
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    result_json = json.loads(r.text)
    print(result_json["result"])
