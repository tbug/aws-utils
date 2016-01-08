#!/usr/bin/env python
import os
import sys
import re
from shutil import copyfile
from StringIO import StringIO


try:
    import click
except ImportError:
    print('failed to import dependency "click"')
    sys.exit(1)
try:
    import boto3
except ImportError:
    print('failed to import dependency "boto3"')
    sys.exit(1)

#
#   Options
# --------------------------
#

# prefix name for the ssh config host directive
name_prefix = os.environ.get(
    'HOST_NAME_PREFIX', ''
)

# base path to credentials.
credentials_path_prefix = os.environ.get(
    'CREDENTIALS_PATH', '~/.billy/creds'
)

# map AMIs to the username used to log in
ami_to_username = {
    'ami-d05e75b8': 'ubuntu'
}

boundary_start = " ----- start of autogenerated from aws vpc -----"
boundary_end = " ----- end of autogenerated from aws vpc -----"


#
# --------------------------
#

def pretty_string(s):
    s = re.sub(r'[^\w\s_-]+', '', s)
    return re.sub(r'[ -]+', '-', s.lower())

def create_ec2():
    client = boto3.client('ec2')
    return client

class Instance(object):
    def __init__(self, details, parent_list):
        self._details = details
        self._parent_list = parent_list

    id = property(lambda s: s._details['InstanceId'])
    private_ip = property(lambda s: s._details['PrivateIpAddress'])
    public_ip = property(lambda s: s._details['PublicIp'])
    state = property(lambda s: s._details['State']['Name'])
    tags = property(
        lambda s: dict(map(
            lambda pairs: (pairs['Key'], pairs['Value']), s._details['Tags'])))
    zone = property(lambda s: s._details['Placement']['AvailabilityZone'])
    image = property(lambda s: s._details['ImageId'])
    key_name = property(lambda s: s._details['KeyName'])

    def __str__(self):
        return str(self.__unicode__())

    def __unicode__(self):
        return u'{}\t{:15s}\t{}'.format(
            self.id,
            self.private_ip,
            self.get_sshconfig_host_value(),
        )

    def get_sshconfig_host_value(self):
        def magic(keyer):
            same_named = []
            instance_value = pretty_string(keyer(self))
            for i in self._parent_list:
                name = pretty_string(keyer(i) or "")
                if name == instance_value:
                    same_named.append(i)
            instance_number = same_named.index(self)+1
            has_collisions = len(same_named) > 1
            if has_collisions:
                return u'%s-%d' % (instance_value, instance_number)
            else:
                return instance_value
        if self.tags.get('Name'):
            return name_prefix + magic(lambda s: s.tags.get('Name'))
        else:
            return name_prefix + magic(lambda s: s.id)


class InstanceList(object):
    def __init__(self, result):
        self._result = result
        self._instances = []
        for reservation in result['Reservations']:
            for instance in reservation['Instances']:
                self._instances.append(Instance(instance, self))
        self._instances.sort(key=lambda i: i.id)

    instances = property(lambda: self._instances)

    def __iter__(self):
        return iter(self._instances)


def get_running_instances():
    ec2 = create_ec2()
    response = ec2.describe_instances(
        Filters=[
            { 'Name': 'instance-state-name',
              'Values': ['running']}
        ],
        MaxResults=1000
    )
    return InstanceList(response)


def username_for_instance(instance):
    return ami_to_username.get(instance.image, 'ubuntu')

def identity_file_for_instance(instance):
    return "{0}/{1}.pem".format(credentials_path_prefix, instance.key_name)

def generate_ssh_config():
    template = u"""Host {name} {hostname}
    HostName {hostname}
    user {user}
    IdentityFile {identity_file}
"""
    running = get_running_instances()
    parts = []
    for instance in running:
        name = instance.get_sshconfig_host_value()
        user = username_for_instance(instance)
        ident = identity_file_for_instance(instance)
        part = template.format(name=name, hostname=instance.private_ip, user=user, identity_file=ident)
        parts.append((name, part))
    parts = map(lambda p: p[1], sorted(parts, key=lambda p: p[0]))
    cfg = '\n#{}\n{}\n#{}\n'.format(boundary_start, '\n'.join(parts), boundary_end)
    return cfg


@click.group()
def cli():
    pass

@cli.command()
def running():
    running = get_running_instances()
    for instance in running:    
        click.echo(instance)

@cli.command()
@click.option('--config', help='ssh config path to patch')
def sshconfig(config):
    cfg = generate_ssh_config()

    if config is None:
        click.echo(cfg)
    else:
        cfglines = StringIO(cfg+'\n').readlines()
        # patch file at config
        current = []
        with open(config, 'r') as f:
            current = f.readlines()
        start_line = '#%s\n' % boundary_start
        end_line = '#%s\n' % boundary_end

        start_idx = None
        end_idx = None

        try:
            start_idx = current.index(start_line)
            end_idx = current.index(end_line)
        except ValueError:
            pass

        # create backup
        copyfile(config, config+'.backup')
        click.echo('created a backup ssh config at %s' % config+'.backup')

        if start_idx and end_idx:
            new = current[:start_idx] + cfglines + current[end_idx+1:]
            click.echo('patching config')
        else:
            new = current + cfglines 
            click.echo('appending to config')
        new_cfg = ''.join(new)

        with open(config, 'w') as f:
            f.write(new_cfg)
        click.echo('ok')


if __name__ == '__main__':
    print("You should not call this file directly")
    cli()
