import unittest
import logging
import requests
import time
import datetime
import os
import json
import warnings
import base64

# from test.bq import log_duration, Client
from .utilities import Utilities
from terra_notebook_utils import drs


''' Defining some environment specific domain constants'''
STAGE = os.environ.get('BDCAT_STAGE', 'staging')
if STAGE == 'prod':
    GEN3_DOMAIN = 'https://gen3.biodatacatalyst.nhlbi.nih.gov'
    RAWLS_DOMAIN = 'https://rawls.dsde-prod.broadinstitute.org'
    ORC_DOMAIN = 'https://firecloud-orchestration.dsde-prod.broadinstitute.org'
    BILLING_PROJECT = 'broad-integration-testing'
elif STAGE == 'staging':
    GEN3_DOMAIN = 'https://staging.gen3.biodatacatalyst.nhlbi.nih.gov'
    RAWLS_DOMAIN = 'https://rawls.dsde-alpha.broadinstitute.org'
    ORC_DOMAIN = 'https://firecloud-orchestration.dsde-alpha.broadinstitute.org'
    BILLING_PROJECT = 'drs-billing-project'
else:
    raise ValueError('Please set BDCAT_STAGE to "prod" or "staging".')

logger = logging.getLogger(__name__)


class TestTerra(unittest.TestCase):
    ''' These are tests that map interactions from other platforms into Terra'''

    def setUp(self):
        # Stolen shamelessly: https://github.com/DataBiosphere/terra-notebook-utils/pull/59
        # Suppress the annoying google gcloud _CLOUD_SDK_CREDENTIALS_WARNING warnings
        warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")
        # Suppress unclosed socket warnings
        warnings.simplefilter("ignore", ResourceWarning)

    @classmethod
    def setUpClass(cls):
        gcloud_cred_dir = os.path.expanduser('~/.config/gcloud')
        if not os.path.exists(gcloud_cred_dir):
            os.makedirs(gcloud_cred_dir, exist_ok=True)
        with open(os.path.expanduser('~/.config/gcloud/application_default_credentials.json'), 'w') as f:
            f.write(base64.decodebytes(os.environ['TEST_MULE_CREDS'].encode('utf-8')).decode('utf-8'))
        print(f'Terra [{STAGE}] Health Status:\n\n{json.dumps(Utilities.check_terra_health(ORC_DOMAIN), indent=4)}')

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            Utilities.delete_workflow_presence_in_terra_workspace(RAWLS_DOMAIN, BILLING_PROJECT)
        except:  # noqa
            pass

    # @retry(errors={requests.exceptions.HTTPError}, error_codes={409})
    def test_dockstore_import_in_terra(self):
        # import the workflow into terra
        response = Utilities.import_dockstore_wf_into_terra(RAWLS_DOMAIN, BILLING_PROJECT)
        method_info = response['methodConfiguration']['methodRepoMethod']
        with self.subTest('Dockstore Import Response: sourceRepo'):
            self.assertEqual(method_info['sourceRepo'], 'dockstore')
        with self.subTest('Dockstore Import Response: methodPath'):
            self.assertEqual(method_info['methodPath'], 'github.com/DataBiosphere/topmed-workflows/UM_aligner_wdl')
        with self.subTest('Dockstore Import Response: methodVersion'):
            self.assertEqual(method_info['methodVersion'], '1.32.0')

        # check that a second attempt gives a 409 error
        try:
            Utilities.import_dockstore_wf_into_terra(RAWLS_DOMAIN, BILLING_PROJECT)
        except requests.exceptions.HTTPError as e:
            with self.subTest('Dockstore Import Response: 409 conflict'):
                self.assertEqual(e.response.status_code, 409)

        # check status that the workflow is seen in terra
        wf_seen_in_terra = Utilities.check_workflow_seen_in_terra(RAWLS_DOMAIN, BILLING_PROJECT)
        with self.subTest('Dockstore Check Workflow Seen'):
            self.assertTrue(wf_seen_in_terra)

        # delete the workflow
        Utilities.delete_workflow_presence_in_terra_workspace(RAWLS_DOMAIN, BILLING_PROJECT)

        # check status that the workflow is no longer seen in terra
        wf_seen_in_terra = Utilities.check_workflow_seen_in_terra(RAWLS_DOMAIN, BILLING_PROJECT)
        with self.subTest('Dockstore Check Workflow Not Seen'):
            self.assertFalse(wf_seen_in_terra)

    @unittest.skip('This test needs to be updated.')
    def test_drs_workflow_in_terra(self):
        """This test runs md5sum in a fixed workspace using a drs url from gen3."""
        response = Utilities.run_workflow(RAWLS_DOMAIN, BILLING_PROJECT, STAGE)
        status = response['status']
        with self.subTest('Dockstore Workflow Run Submitted'):
            self.assertEqual(status, 'Submitted')
        with self.subTest('Dockstore Workflow Run Responds with DRS.'):
            self.assertTrue(response['workflows'][0]['inputResolutions'][0]['value'].startswith('drs://'))

        submission_id = response['submissionId']

        # md5sum should run for about 4 minutes, but may take far longer(?); give a generous timeout
        # also configurable manually via MD5SUM_TEST_TIMEOUT if held in a pending state
        start = time.time()
        deadline = start + int(os.environ.get('MD5SUM_TEST_TIMEOUT', 60 * 60))
        ''' UNCOMMENT THIS TOO'''
        # table = f'platform-dev-178517.bdc.terra_md5_latency_min_{STAGE}'
        while True:
            response = Utilities.check_workflow_status(rawls_domain=RAWLS_DOMAIN, billing_project=BILLING_PROJECT, submission_id=submission_id)
            status = response['status']
            if response['workflows'][0]['status'] == "Failed":
                '''WHEN THIS GOES LIVE UNCOMMENT'''
                # log_duration(table, time.time() - start)
                raise RuntimeError(f'The md5sum workflow did not succeed:\n{json.dumps(response, indent=4)}')
            elif status == 'Done':
                break
            else:
                now = time.time()
                if now < deadline:
                    print(f"md5sum workflow state is: {response['workflows'][0]['status']}. "
                          f"Checking again in 20 seconds.")
                    time.sleep(20)
                else:
                    print(json.dumps(response, indent=4))
                    '''WHEN THIS GOES LIVE UNCOMMENT'''
                    # log_duration(table, time.time() - start)
                    raise RuntimeError('The md5sum workflow run timed out.  '
                                       f'Expected 4 minutes, but took longer than '
                                       f'{float(now - start) / 60.0} minutes.')
        '''WHEN THIS GOES LIVE UNCOMMENT'''
        # log_duration(table, time.time() - start)
        with self.subTest('Dockstore Workflow Run Completed Successfully'):
            if response['workflows'][0]['status'] != "Succeeded":
                raise RuntimeError(f'The md5sum workflow did not succeed:\n{json.dumps(response, indent=4)}')

    def test_pfb_handoff_from_gen3_to_terra(self):
        time_stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
        workspace_name = f'integration_test_pfb_gen3_to_terra_{time_stamp}_delete_me'
        job_id = 0

        with self.subTest('Create a terra workspace.'):
            response = Utilities.create_terra_workspace(rawls_domain=RAWLS_DOMAIN, billing_project=BILLING_PROJECT, workspace=workspace_name)
            self.assertTrue('workspaceId' in response)
            self.assertTrue(response['createdBy'] == 'biodata.integration.test.mule@gmail.com')

        with self.subTest('Import static pfb into the terra workspace.'):
            response = Utilities.import_pfb(workspace=workspace_name,
                                            pfb_file='https://cdistest-public-test-bucket.s3.amazonaws.com/export_2020-06-02T17_33_36.avro',
                                            orc_domain=ORC_DOMAIN,
                                            billing_project=BILLING_PROJECT)
            job_id = response['jobId']
            self.assertTrue('jobId' in response)

        with self.subTest('Check on the import static pfb job status.'):
            response = Utilities.pfb_job_status_in_terra(workspace=workspace_name, job_id=job_id, orc_domain=ORC_DOMAIN, billing_project=BILLING_PROJECT)
            # this should take < 60 seconds
            while response['status'] in ['Translating', 'ReadyForUpsert', 'Upserting', 'Pending']:
                time.sleep(2)
                response = Utilities.pfb_job_status_in_terra(workspace=workspace_name, job_id=job_id, orc_domain=ORC_DOMAIN, billing_project=BILLING_PROJECT)
            self.assertTrue(response['status'] == 'Done',
                            msg=f'Expecting status: "Done" but got "{response["status"]}".\n'
                                f'Full response: {json.dumps(response, indent=4)}')

        with self.subTest('Delete the terra workspace.'):
            response = Utilities.delete_terra_workspace(workspace=workspace_name, rawls_domain=RAWLS_DOMAIN, billing_project=BILLING_PROJECT)
            if not response.ok:
                raise RuntimeError(
                    f'Could not delete the workspace "{workspace_name}": [{response.status_code}] {response}')
            if response.status_code != 202:
                logger.critical(f'Response {response.status_code} has changed: {response}')
            response = Utilities.delete_terra_workspace(workspace=workspace_name, rawls_domain=RAWLS_DOMAIN, billing_project=BILLING_PROJECT)
            self.assertTrue(response.status_code == 404)

    @unittest.skip('There seems to be an environment issue with this test in staging.')
    def test_public_data_access(self):
        # this DRS URI only exists on staging/alpha and requires os.environ['TERRA_DEPLOYMENT_ENV'] = 'alpha'
        drs.head('drs://dg.712C/fa640b0e-9779-452f-99a6-16d833d15bd0',
                 workspace_name='DRS-Test-Workspace', workspace_namespace=BILLING_PROJECT)

    @unittest.skip('This test needs to be updated.')
    def test_controlled_data_access(self):
        # this DRS URI only exists on staging/alpha and requires os.environ['TERRA_DEPLOYMENT_ENV'] = 'alpha'
        drs.head('drs://dg.712C/04fbb96d-68c9-4922-801e-9b1350be3b94',
                 workspace_name='DRS-Test-Workspace', workspace_namespace=BILLING_PROJECT)


if __name__ == '__main__':
    test_runner = TestTerra()
    test_result = unittest.TestResult()
    test_runner.run(result=test_result)
    print(test_result)
