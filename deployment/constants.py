# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# Keep all the constants needed for multiple stacks here
import os
# account and region
acc = os.getenv('CDK_DEFAULT_ACCOUNT')
region = os.getenv('CDK_DEFAULT_REGION')
app_prefix = 'papi-kv'
source_dir = f"{os.path.dirname(os.path.abspath(__file__))}/../source"
assets_dir = f"{os.path.dirname(os.path.abspath(__file__))}/../assets"
sol_id = "SO9463"
stack_desc = f"Guidance for Implementing Google Privacy Sandbox Key/Value Service on AWS ({sol_id})"
papi_repo_url = "https://github.com/privacysandbox/protected-auction-key-value-service"
awscli_cntr_tag = "papi-datacli-with-awscli"
python_cntr_tag = "papi-datacli-with-python"