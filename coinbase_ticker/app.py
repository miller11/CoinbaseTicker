import os
from botocore.config import Config
from AccountSummaryUtil import AccountSummaryUtil
import boto3
import time

TABLE_NAME = 'ross-gains'
DATABASE_NAME = 'realized-gains'
CURRENT_MILLI_TIME = round(time.time() * 1000)


def build_record(r_dimensions, r_name, r_value):
    return {
        'Dimensions': r_dimensions,
        'MeasureName': r_name,
        'MeasureValue': str(r_value),
        'MeasureValueType': 'DOUBLE',
        'Time': str(CURRENT_MILLI_TIME)
    }


def lambda_handler(event, context):
    print(event)
    print("################################################################")
    print(context)

    # pull ssm param for jira account
    ssm = boto3.client('ssm', region_name='us-east-1')
    api_key = ssm.get_parameter(Name='/ic-miller/realized-coinbase/coinbase/api-key', WithDecryption=True)['Parameter']['Value']
    api_secret = ssm.get_parameter(Name='/ic-miller/realized-coinbase/coinbase/api-secret', WithDecryption=True)['Parameter']['Value']

    summary_util = AccountSummaryUtil(api_key, api_secret)

    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_KEY_SECRET'),
    )

    client = session.client('timestream-write', config=Config(read_timeout=20, max_pool_connections=5000,
                                                              retries={'max_attempts': 10}))

    records = []
    account_dimensions = [
        {'Name': 'wallet', 'Value': 'ross'},
        {'Name': 'type', 'Value': 'account'}
    ]

    # gain
    records.append(build_record(account_dimensions, 'gain', summary_util.get_total_gains().amount))
    # balance
    records.append(build_record(account_dimensions, 'balance', summary_util.get_current_balance().amount))
    # investment
    records.append(build_record(account_dimensions, 'investment', summary_util.get_current_investment().amount))

    for account_summary in summary_util.get_acct_summaries():
        dimensions = [
            {'Name': 'wallet', 'Value': 'ross'},
            {'Name': 'type', 'Value': account_summary['name']}
        ]

        # gain
        records.append(build_record(dimensions, 'gain', account_summary['realized_gains'].amount))
        # balance
        records.append(build_record(dimensions, 'balance', account_summary['balance'].amount))
        # investment
        records.append(build_record(dimensions, 'investment', account_summary['investment'].amount))

    try:
        result = client.write_records(DatabaseName=DATABASE_NAME, TableName=TABLE_NAME, Records=records, CommonAttributes={})
        print("WriteRecords Status: [%s]" % result['ResponseMetadata']['HTTPStatusCode'])
    except client.exceptions.RejectedRecordsException as err:
        print("ERROR RejectedRecords: ", err)
        for rr in err.response["RejectedRecords"]:
            print("Rejected Index " + str(rr["RecordIndex"]) + ": " + rr["Reason"])
        print("Other records were written successfully. ")
    except Exception as err:
        print("ERROR:", err)


