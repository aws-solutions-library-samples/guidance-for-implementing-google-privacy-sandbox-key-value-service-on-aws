# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This is th entry point script of the docker image
# app takes four parameters
# 1 s3 input bucket 2 key with file name for input
# 3 s3 output bucket 4 key *without* file name for output
import boto3
import os
import logging
from pathlib import Path
import datetime
from botocore.exceptions import ClientError, ParamValidationError
import subprocess
from shlex import split
from sys import exit

logger = logging.getLogger(__name__)

def app(inps3bucket: str,inps3key: str,outs3bucket: str,outs3key: str) -> None:
    inpfile = s32local(inps3bucket, inps3key)
    ifname = get_file_name(inpfile)
    outfile = f"/tools/{ifname}_DELTA"
    # cmd = f'cp "{inpfile}" "{outfile}"'
    cmd_str = f"/tools/data_cli/data_cli format_data --input_file={inpfile} --input_format=CSV --output_file={outfile} --output_format=DELTA"
    cmd = split(cmd_str)
    # cmd = ["/tools/data_cli/data_cli", "format_data", f"--input_file={inpfile}", "--input_format=CSV", f"--output_file={outfile}", "--output_format=DELTA"]
    run_command(cmd)
    local2s3(outs3bucket, outs3key, outfile)

def run_command(cmd: list) -> None:
    try:
        logging.info(f"running format conversion command: {cmd}")
        cmd_out = subprocess.run(cmd, stderr=subprocess.STDOUT)
    except subprocess.SubprocessError as e:
        logging.error(f"Command run error : {e}")
        exit(1)
    else:
        if cmd_out.returncode !=0:
            logging.error(f"Command failure output: {cmd_out.stdout}")
            exit(1)
        logging.info(f"Command success output: {cmd_out.stdout}")

def get_file_name(fullpath: str) -> str:
    return fullpath.split("/")[-1]

def s32local(s3bucket: str, s3key) -> str:
    logging.info("S3 to local")
    ifname = get_file_name(s3key)
    inpfile = f"/tools/{ifname}"
    s3 = boto3.client('s3')
    try:
        s3.download_file(s3bucket, s3key, inpfile)
    except ParamValidationError as e:
        logging.error(f"Parameter validation error: {e}")
        exit(1)
    except ClientError as e:
        logging.error(f"Unexpected error: {e}")
        exit(1)
    logger.info("download complete")
    filecheck(inpfile)
    return inpfile

def local2s3(s3bucket: str, s3key:str, localfile: str) -> int:
    logging.info("Local to S3")
    ofname = get_file_name(localfile)
    key = f'{s3key}/{ofname}'
    logger.info(f"Output key: {key}")
    filecheck(localfile)
    s3 = boto3.client('s3')
    try:
        s3.upload_file(localfile, s3bucket, key)
    except ParamValidationError as e:
        logging.error(f"Parameter validation error: {e}")
        exit(1)
    except ClientError as e:
        logging.error(f"Unexpected error: {e}")
        exit(1)
    logger.info("upload complete")
    return 0

def filecheck(localfile: str) -> None:
    try:
        fstat=Path(localfile).stat()
    except os.error as e:
        logging.error(f"Command run error: {e}")
        exit(1)
    mtime = datetime.datetime.fromtimestamp(fstat.st_ctime)
    logger.info(f'last modified time of {localfile}: {mtime}')
    logger.info(f'current time: {datetime.datetime.now()}')
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    inp_s3_bucket = os.getenv("INP_BUCKET")
    inp_s3_key = os.getenv("INP_KEY")
    out_s3_bucket = os.getenv("OUT_BUCKET")
    out_s3_key = os.getenv("OUT_KEY")
    logger.info(f"inputs: {inp_s3_bucket} {inp_s3_key} {out_s3_bucket} {out_s3_key}")
    app(inp_s3_bucket, inp_s3_key, out_s3_bucket, out_s3_key)