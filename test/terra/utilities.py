import json
import requests
from terra_notebook_utils import gs
from unittest import TestResult


class Utilities:
    '''Usually Atomic actions that should be covered in platform specific Unit tests '''

    def report_out(results: TestResult, webhook: str):
        result_text = f'''
        Tests Run: {results.testsRun}
        Tests Failed: {len(results.failures)}
        Test Errors: {len(results.errors)}
        List of tests failed: {", ".join([x[0] for x in results.failures])}
        List of tests errored: {", ".join([x[0] for x in results.errors])}'''
        requests.post(webhook, json={'text': result_text})

    def check_terra_health(orc_domain):
        # note: the same endpoint seems to be at: https://api.alpha.firecloud.org/status
        endpoint = f'{orc_domain}/status'

        resp = requests.get(endpoint)
        resp.raise_for_status()
        return resp.json()

    def import_dockstore_wf_into_terra(rawls_domain, billing_project):
        workspace = 'BDC_Dockstore_Import_Tester'
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}/methodconfigs'

        token = gs.get_access_token()
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        data = {
            "namespace": billing_project,
            "name": "UM_aligner_wdl",
            "rootEntityType": "",
            "inputs": {},
            "outputs": {},
            "prerequisites": {},
            "methodRepoMethod": {
                "sourceRepo": "dockstore",
                "methodPath": "github.com/DataBiosphere/topmed-workflows/UM_aligner_wdl",
                "methodVersion": "1.32.0"
            },
            "methodConfigVersion": 1,
            "deleted": False
        }

        resp = requests.post(endpoint, headers=headers, data=json.dumps(data))
        
        resp.raise_for_status()
        return resp.json()

    def check_workflow_presence_in_terra_workspace(rawls_domain, billing_project):
        workspace = 'BDC_Dockstore_Import_Tester'
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}/methodconfigs?allRepos=true'

        token = gs.get_access_token()
        headers = {'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        resp = requests.get(endpoint, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def delete_workflow_presence_in_terra_workspace(rawls_domain, billing_project):
        workspace = 'BDC_Dockstore_Import_Tester'
        workflow = 'UM_aligner_wdl'
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}/methodconfigs/{billing_project}/{workflow}'

        token = gs.get_access_token()
        headers = {'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        resp = requests.delete(endpoint, headers=headers)
        resp.raise_for_status()
        return {}

    def run_workflow(rawls_domain, billing_project, stage):
        workspace = 'DRS-Test-Workspace'
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}/submissions'

        token = gs.get_access_token()
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        # staging input: https://gen3.biodatacatalyst.nhlbi.nih.gov/files/dg.712C/fa640b0e-9779-452f-99a6-16d833d15bd0
        # md5sum: e87ecd9c771524dcc646c8baf6f8d3e2
        data = {
            "methodConfigurationNamespace": "drs_tests",
            "methodConfigurationName": "md5sum",
            "expression": "this.data_access_test_drs_uriss",
            "useCallCache": False,
            "deleteIntermediateOutputFiles": True,
            "workflowFailureMode": "NoNewCalls"
        }

        resp = requests.post(endpoint, headers=headers, data=json.dumps(data))
        resp.raise_for_status()
        return resp.json()

    def check_workflow_seen_in_terra(rawls_domain, billing_project):
        wf_seen_in_terra = False
        response = Utilities.check_workflow_presence_in_terra_workspace(rawls_domain, billing_project)
        for wf_response in response:
            method_info = wf_response['methodRepoMethod']
            if method_info['methodPath'] == 'github.com/DataBiosphere/topmed-workflows/UM_aligner_wdl' \
                    and method_info['sourceRepo'] == 'dockstore' \
                    and method_info['methodVersion'] == '1.32.0':
                wf_seen_in_terra = True
                break
        return wf_seen_in_terra

    def check_workflow_status(rawls_domain, billing_project, submission_id):
        workspace = 'DRS-Test-Workspace'
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}/submissions/{submission_id}'

        token = gs.get_access_token()
        headers = {'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        resp = requests.get(endpoint, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def create_terra_workspace(rawls_domain, billing_project, workspace):
        endpoint = f'{rawls_domain}/api/workspaces'

        token = gs.get_access_token()
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        data = dict(namespace=billing_project,
                    name=workspace,
                    authorizationDomain=[],
                    attributes={'description': ''},
                    copyFilesWithPrefix='notebooks/')

        resp = requests.post(endpoint, headers=headers, data=json.dumps(data))

        if resp.ok:
            return resp.json()
        else:
            resp.raise_for_status()

    def import_pfb(workspace, pfb_file, orc_domain, billing_project):
        endpoint = f'{orc_domain}/api/workspaces/{billing_project}/{workspace}/importPFB'

        token = gs.get_access_token()
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}
        data = dict(url=pfb_file)

        resp = requests.post(endpoint, headers=headers, data=json.dumps(data))

        if resp.ok:
            return resp.json()
        else:
            resp.raise_for_status()

    def pfb_job_status_in_terra(workspace, job_id, orc_domain, billing_project):
        endpoint = f'{orc_domain}/api/workspaces/{billing_project}/{workspace}/importPFB/{job_id}'
        token = gs.get_access_token()

        headers = {'Accept': 'application/json',
                   'Authorization': f'Bearer {token}'}

        resp = requests.get(endpoint, headers=headers)

        if resp.ok:
            return resp.json()
        else:
            resp.raise_for_status()

    def delete_terra_workspace(workspace, rawls_domain, billing_project):
        endpoint = f'{rawls_domain}/api/workspaces/{billing_project}/{workspace}'

        token = gs.get_access_token()
        headers = {'Accept': 'text/plain',
                   'Authorization': f'Bearer {token}'}

        resp = requests.delete(endpoint, headers=headers)

        return resp
