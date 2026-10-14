"""Existing-image deployment must not start a build or detection workload."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class ExistingImageDeployTests(unittest.TestCase):
    def test_upload_path_uses_saved_image_and_selected_model(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            log = directory / 'calls.jsonl'
            stub = '''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
tool=Path(sys.argv[0]).name
args=sys.argv[1:]
with open(os.environ['TEST_CALLS'],'a') as f:f.write(json.dumps([tool,args])+'\\n')
if tool=='docker':
    if 'buildx' in args or 'build' in args or 'run' in args:sys.exit(99)
    if args[:2]==['image','inspect']:print('linux/amd64')
    if args and args[0]=='login':sys.stdin.read()
elif args[:2]==['sts','get-caller-identity']:print('111122223333')
elif args[:2]==['ecr','describe-repositories']:print('arn:aws:ecr:ap-south-1:111122223333:repository/test')
elif args[:2]==['ecr','get-login-password']:print('synthetic-test-password')
elif args[:2]==['cloudformation','describe-stacks']:
    print('test-api' if any('RestApiId' in a for a in args) else '[]')
'''
            for tool in ['aws', 'docker']:
                path = directory / tool
                path.write_text(stub)
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(directory)+os.pathsep+os.environ['PATH'],
                       TEST_CALLS=str(log), PII_SPACY_MODEL='en_core_web_sm',
                       EXISTING_LOCAL_IMAGE='pii-presidio-lambda:model-test',
                       MEMORY_SIZE='512', PROVISIONED_CONCURRENCY='0',
                       STACK_NAME='pii-sm-test', ECR_REPOSITORY_NAME='pii-sm-test')
            result = subprocess.run(['bash',str(root/'scripts/deploy.sh'),'--deploy-existing-image'],
                                    env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=[json.loads(line) for line in log.read_text().splitlines()]
            docker=[args for tool,args in calls if tool=='docker']
            self.assertTrue(any(args[0]=='tag' and args[1]=='pii-presidio-lambda:model-test' for args in docker))
            self.assertTrue(any(args[0]=='push' for args in docker))
            self.assertFalse(any(args[0] in {'build','buildx','run'} for args in docker))
            deployment=next(args for tool,args in calls if tool=='aws' and args[:2]==['cloudformation','deploy'])
            self.assertIn('SpacyModel=en_core_web_sm',deployment)
            self.assertIn('MemorySize=512',deployment)
            self.assertIn('ProvisionedConcurrency=0',deployment)


if __name__=='__main__':unittest.main()
