#!/usr/bin/env python3

# Imports
import boto3
import datetime
import time
import requests
import subprocess
from operator import itemgetter

# Assigning EC2 variables from boto3
ec2 = boto3.resource('ec2')
ec2client = boto3.client('ec2')

# Assigning S3 variables from boto3
s3 = boto3.resource('s3')
s3client = boto3.client('s3')

# User's name will be used to create bucket
try:
    nameInput = input('Please enter your first name: ')
    # Name must be lowercase for creating bucket name
    name = nameInput.lower()
except Exception as error:
    print('There was an error getting name input: ' + str(error))

# Taking input from user for new key name
validKeyName = False
while validKeyName == False:
    try:
        keyName = input("Please enter a key pair name: ")
        # Checking if keyName exists
        response = ec2client.describe_key_pairs()
        keyPairs = response['KeyPairs']
        valid = True
        for keypair in keyPairs:
            if keypair['KeyName'] == keyName:
                valid = False
                print('Key pair name exists - please try another')
        if valid == True:
            validKeyName = True
    except Exception as error:
        print('There was an error taking key pair input: ' + str(error))

# Creating key pair file
try:
    outfile = open(keyName + '.pem', 'w')
    key_pair = ec2.create_key_pair(KeyName=keyName)
    KeyPairOut = str(key_pair.key_material)
    outfile.write(KeyPairOut)
    outfile.close()
    cmd = 'chmod 400 ' + keyName + '.pem'
    subprocess.run(cmd, shell=True)
    print(keyName + '.pem file created')
except Exception as error:
    print('There was an error creating key pair: ' + str(error))
    quit()

# Checking if httpssh security group exists
try:
    response = ec2client.describe_security_groups()
    secGroups = response['SecurityGroups']
    securityGroupId = None
    for group in secGroups:
        if group['GroupName'] == 'httpssh':
            securityGroupId = group['GroupId']
            print('Using existing security group')
    # If httpssh security group doesn't exist, it is created
    if securityGroupId == None:
        print('Creating new security group..')
        securityGroup = ec2client.create_security_group(
            Description='HTTP and SSH',
            GroupName='httpssh'
        )
        securityGroupId = securityGroup['GroupId']
        ec2client.authorize_security_group_ingress(
            GroupId=securityGroupId,
            # Allowing incoming traffic through HTTP and SSH
            IpPermissions=[
                {
                    'FromPort': 22,
                    'IpProtocol': 'tcp',
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0'
                        },
                    ],
                    'ToPort': 22
                },
                {
                    'FromPort': 80,
                    'IpProtocol': 'tcp',
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0'
                        },
                    ],
                    'ToPort': 80
                }
            ]
        )
        print('Security group created')
except Exception as error:
    print('There was an error creating security group: ' + str(error))
    quit()

# Getting latest Amazon Linux 2 AMI id
print('Getting latest AMI..')
try:
    response = ec2client.describe_images(
        Filters=[
            {
                'Name': 'description',
                'Values': [
                    'Amazon Linux 2 AMI*',
                ]
            },
        ],
        Owners=[
            'amazon'
        ]
    )
    image_details = sorted(response['Images'], key=itemgetter(
        'CreationDate'), reverse=True)
    ami_id = image_details[0]['ImageId']
    print('Latest AMI found: ' + ami_id)
except Exception as error:
    print('There was an error getting the latest AMI: ' + str(error))
    quit()

# Creating EC2 instance
try:
    print('Creating EC2 instance..')
    instances = ec2.create_instances(
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.nano',
        SecurityGroupIds=[
            securityGroupId,
        ],
        KeyName=keyName,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                                'Value': 'Web Server'
                    }
                ]
            }
        ],
        UserData="""
            #!/bin/bash
            yum update -y
            yum install httpd -y
            systemctl enable httpd
            systemctl start httpd
            service sshd restart
            """
    )
    instance = instances[0]
    instance_id = instance.id
    print('EC2 instance created: ' + instance_id)
except Exception as error:
    print('There was an error creating EC2 instance: ' + str(error))
    quit()

# Waiter used to wait until instance is running
print('Launching instance..')
instance.wait_until_running()
instance.reload()

# Get public IP address of instance
instance_ip = instance.public_ip_address
print('Instance launched: ' + instance_ip)

# Assigning current timestamp to the date variable
date = datetime.datetime.now()
# String with formatted date
bucket_name = name + "s-bucket-" + date.strftime("%d%m%y%f")

# Creating bucket with bucket_name variable
try:
    print('Creating S3 bucket..')
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
                     'LocationConstraint': 'eu-west-1'})
    # Waits until bucket exists
    waiter = s3client.get_waiter('bucket_exists')
    waiter.wait(
        Bucket=bucket_name
    )
    print('S3 bucket created: ' + bucket_name)
except Exception as error:
    print('There was an error creating the S3 bucket: ' + str(error))
    quit()

# Getting image from URL using requests and saving it to working directory
try:
    url = 'http://devops.witdemo.net/image.jpg'
    print('Retrieving image from ' + url + '..')
    filename = url.split("/")[-1]
    r = requests.get(url, timeout=0.5)
    if r.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(r.content)
    print('Image retrieved')
except Exception as error:
    print('There was an error getting image: ' + str(error))
    quit()

# Uploading image to S3 bucket
try:
    key = 'image.jpg'
    print('Uploading ' + filename + ' to ' + bucket_name)
    try:
        s3.Bucket(bucket_name).upload_file(
            'image.jpg', key, ExtraArgs={'ACL': 'public-read'})
        print('Image uploaded')
    except Exception as error:
        print(error)
except Exception as error:
    print('There was an error uploading image to bucket: ' + str(error))
    quit()

# Creating image URL using bucket name and key name
image_url = "https://s3-eu-west-1.amazonaws.com/%s/%s" % (bucket_name, key)

# Command for writing index.html file
indexCommands = '''
echo "<html>" > index.html
echo "<h1>Welcome %s!</h1>" > index.html
echo "Availability zone: " >> index.html
curl http://169.254.169.254/latest/meta-data/placement/availability-zone >> index.html
echo "<br>Hostname: " >> index.html
curl http://169.254.169.254/latest/meta-data/hostname >> index.html
echo "<br>MAC address: " >> index.html
curl http://169.254.169.254/latest/meta-data/mac >> index.html
echo "<br>Instance type: " >> index.html
curl http://169.254.169.254/latest/meta-data/instance-type >> index.html
echo "<br>Private IP address: " >> index.html
curl http://169.254.169.254/latest/meta-data/local-ipv4 >> index.html
echo "<br><br>Here is the image:<br> " >> index.html
echo "<img src="%s">" >> index.html
''' % (name.capitalize(), image_url)

# Using while loop to attempt SSH into instance every 5 seconds - max of 10 attempts
try:
    print('Connecting to EC2 instance via SSH - please wait..')
    cmdIndex = "ssh -o StrictHostKeyChecking=no -i " + keyName + \
        ".pem ec2-user@" + instance_ip + " '" + indexCommands + "'"
    sshSuccess = 0
    sshAttempts = 1
    while sshSuccess == 0:
        if sshAttempts <= 10:
            time.sleep(5)
            response = subprocess.run(
                cmdIndex, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if response.returncode == 0:
                sshSuccess = 1
                print('SSH connection successful')
            else:
                sshAttempts += 1
        else:
            print('Connection to EC2 instance via SSH could not be made.')
            quit()
except Exception as error:
    print('There was an error connecting to EC2 instance via SSH: ' + str(error))
    quit()

# Using while loop to attempt copying index.html file to /var/www/html directory every 15 secondsgg
try:
    print('Copying index.html to EC2 instance - please wait..')
    copySuccess = 0
    copyAttempts = 1
    cmdCopy = "ssh -i " + keyName + ".pem ec2-user@" + \
        instance_ip + " 'sudo cp index.html /var/www/html'"
    while copySuccess == 0:
        if copyAttempts <= 10:
            time.sleep(15)
            response = subprocess.run(
                cmdCopy, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if response.returncode == 0:
                copySuccess = 1
                print('index.html copied successfully')
            else:
                copyAttempts += 1
        else:
            print('index.html could not be copied to EC2 instance.')
            quit()
except Exception as error:
    print('There was an error copying index.html to EC2 instance: ' + str(error))
    quit()

# Copying monitor.sh file to instance using secure copy
try:
    print('Copying monitor.sh file to EC2 instance - please wait..')
    cmd1 = "scp -i " + keyName + ".pem monitor.sh ec2-user@" + instance_ip + ":."
    subprocess.run(cmd1, shell=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    print('monitor.sh copied successfully')
except Exception as error:
    print('There was an error copying monitor.sh to EC2 instance: ' + str(error))
    quit()

# Updating permissions on monitor.sh file on instance
try:
    print('Updating permissions on monitor.sh..')
    cmd2 = "ssh -i " + keyName + ".pem ec2-user@" + \
        instance_ip + " 'chmod 700 monitor.sh'"
    subprocess.run(cmd2, shell=True)
    print('monitor.sh permissions updated')
except Exception as error:
    print('There was an error updating permissions on monitor.sh: ' + str(error))
    quit()

# Running monitor.sh file
try:
    print('Running monitor.sh..')
    cmd3 = "ssh -i " + keyName + ".pem ec2-user@" + instance_ip + " './monitor.sh'"
    print('')
    subprocess.run(cmd3, shell=True)
    print('')
except Exception as error:
    print('There was an error running monitor.sh: ' + str(error))
    quit()

# Running cloudwatch.py file to monitor instance
try:
    print('Running cloudwatch.py to monitor EC2 instance - instance will be monitored for 6 minutes..')
    subprocess.run('python3 ./cloudwatch.py ' + instance_id, shell=True)
except Exception as error:
    print('Error running cloudwatch.py: ' + str(error))
