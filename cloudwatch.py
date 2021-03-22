#!/usr/bin/env python3

# Imports
import boto3
from datetime import datetime, timedelta
import time
import sys

cloudwatch = boto3.resource('cloudwatch')
ec2 = boto3.resource('ec2')

instance_id = sys.argv[1]
instance = ec2.Instance(instance_id)

instance.monitor()
time.sleep(360)

metric_iterator = cloudwatch.metrics.filter(Namespace='AWS/EC2',
                                            MetricName='CPUUtilization',
                                            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}])

metric = list(metric_iterator)[0]

response = metric.get_statistics(StartTime=datetime.utcnow() - timedelta(minutes=5),
                                 EndTime=datetime.utcnow(),
                                 Period=300,
                                 Statistics=['Average'])

print("Average CPU utilisation:",
      response['Datapoints'][0]['Average'], response['Datapoints'][0]['Unit'])