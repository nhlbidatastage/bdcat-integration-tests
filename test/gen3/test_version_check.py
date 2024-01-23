#!/usr/bin/env python3
import logging
import os
import requests
import unittest
import sys
import datetime

from ..bq import Client

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
log = logging.getLogger(__name__)


bdcat_prod_url = "https://gen3.biodatacatalyst.nhlbi.nih.gov"
bdcat_staging_url = "https://staging.gen3.biodatacatalyst.nhlbi.nih.gov"


class TestGen3VersionsAcrossEnvironments(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        '''COMMENT FOR LOCAL TESTING'''
        gcloud_cred_dir = os.path.expanduser('~/.config/gcloud')
        if not os.path.exists(gcloud_cred_dir):
            os.makedirs(gcloud_cred_dir, exist_ok=True)
        '''END COMMENT FOR LOCAL TESTING'''

    def test_staging_versus_prod_version(self):
        '''
        Assertions around release versions.

        It is acceptable for BDCat staging to be on the same version or ahead
        of BDCat PROD.
        If PROD is updated before staging, that means a new version
        has been released without proper cross-org testing.

        >>> bdcat_prod_version = "2021.12"
        >>> bdcat_staging_version = "2022.01"
        >>> bdcat_staging_version >= bdcat_prod_version
        True
        >>> bdcat_prod_version = "2021.05"
        >>> bdcat_staging_version = "2021.04"
        >>> bdcat_staging_version >= bdcat_prod_version
        False
        >>> bdcat_staging_version = "2021.06"
        >>> bdcat_prod_version = "2021.05"
        >>> bdcat_staging_version >= bdcat_prod_version
        True
        '''
        log.info("checking the gen3 release version on bdcat prod...")
        bdcat_prod_version_json = requests.get(
            f"{bdcat_prod_url}/index/_version"
        ).json()
        # extract version from json payload
        bdcat_prod_version = bdcat_prod_version_json['version']

        log.info("checking the gen3 release version on bdcat staging...")
        bdcat_staging_version_json = requests.get(
            f"{bdcat_staging_url}/index/_version"
        ).json()
        bdcat_staging_version = bdcat_staging_version_json['version']

        self.assertGreaterEqual(bdcat_staging_version, bdcat_prod_version)


if __name__ == "__main__":

    test_list = {'test_staging_versus_prod_version': ''}

    results = unittest.main(exit=False)
    timestamp = datetime.datetime.now()
    client = Client()
    all_failures = results.result.errors.extend(results.result.failures)
    if all_failures is not None:
        for test, status in all_failures:
            # Unfortunately this is the only way to get the test method name from the TestCase
            test_name = test._testMethodName
            del test_list[test_name]
            try:
                # To create tables, skip all tests and set create to True:
                client.log_test_results(test_name, "failure", timestamp, create=True)
            except Exception as e:
                log.exception('Failed to log test %r', test, exc_info=e)
    for test_name in test_list.keys():
        try:
            # To create tables, skip all tests and set create to True:
            client.log_test_results(test_name, "success", timestamp, create=True)
        except Exception as e:
            log.exception('Failed to log test %r', test, exc_info=e)
    sys.exit(not results.result.wasSuccessful())
