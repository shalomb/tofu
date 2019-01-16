#!/usr/bin/python

# TODO
# As per http://docs.ansible.com/ansible/latest/dev_guide/developing_inventory.html
# Support
#   --host

'''
Dynamic inventory for ansible using terraform state
'''

from __future__ import print_function
import argparse
import os
import re
import subprocess
import sys
import yaml


try:
  import json
except ImportError:
  import simplejson as json



def warn(*args, **kwargs):
  if 'TF_DEBUG' in os.environ:
    print(*args, file=sys.stderr, **kwargs)

def die(*args, **kwargs):
  warn(*args, **kwargs)
  sys.exit(126)

def print_json(obj):
  print( json.dumps(obj, indent=2, sort_keys=True) )

class Dotable(dict):
  '''
  Convert any dict/map into a dotable datastructure to make accessing
  attributes easy/elegant and less clumsy.
  src: [Dot notation in python nested dictionaries]
       (https://hayd.github.io/2013/dotable-dictionaries)
  '''

  __getattr__= dict.__getitem__

  def __init__(self, d):
    self.update(**dict((k, self.parse(v))
      for k, v in d.iteritems()))

  @classmethod
  def parse(cls, v):
    if isinstance(v, dict):
      return cls(v)
    elif isinstance(v, list):
      return [cls.parse(i) for i in v]
    else:
      return v

class TerraformInventory(object):

  class TerraformException(Exception):
    pass

  class TerraformStateException(Exception):
    pass

  def get_resources(self, type='openstack_compute_instance_v2'):
    return filter( lambda x : re.search(type, x), self.resources.keys() )


  def __init__(self):
    self.inventory = {}

    if 'TF_STATE_JSON' in os.environ:
      warn("Sourcing terraform state from file: %s" % os.environ['TF_STATE_JSON'])
      try:
        content = open(os.environ['TF_STATE_JSON'])
      except FileNotFoundError as e:
        warn("File not found: %s, %s" % os.environ['TF_STATE_JSON'], str(e))
        sys.exit(3)
      self.data = json.load(content)
    else:
      warn("TF_STATE_JSON empty")
      warn("Sourcing terraform state by executing `terraform state pull`")
      try:
        out = subprocess.check_output(['terraform', 'state', 'pull'])
        if not out or not len(out):
          warn('terraform returned empty state (no state).')
          raise self.TerraformStateException('''
            Ensure terraform state is accessible: `terraform state pull`
            Ensure terraform configuration is consistent: `terraform validate`
            Ensure terraform can list state: `terraform state list`, `terraform show`
            Ensure (remote) state provider is accessible.
            Ensure %s is run in the correct directory: `cd %s && ls -ld .terraform/*tfstate`
            Ensure terraform is initialised: `terraform init && terraform state pull`
          ''' % (__file__, os.path.dirname(os.path.realpath(__file__)))
          )
        self.data = json.loads(out)
      except OSError as e:
        if e.errno == os.errno.ENOENT:
          err = "terraform does not appear to be installed: %s" % str(e)
          warn(err)
          raise self.TerraformException(err)
        else:
          raise self.TerraformException(e)

    self.data = Dotable.parse( self.data )
    self.resources = Dotable.parse( self.data.modules[0].resources )
    self.instances = self.get_resources(type='openstack_compute_instance_v2')


  def print_hosts_file(self):
    v6_hosts = [
      ( self.resources[x].primary.attributes.access_ip_v6,
        self.resources[x].primary.attributes.name
      ) for x in self.instances ]
    v4_hosts = [
      ( self.resources[x].primary.attributes.access_ip_v4,
        self.resources[x].primary.attributes.name
      ) for x in self.instances ]
    combined = [ x for x in filter(lambda y: y[0], (v6_hosts + v4_hosts)) ]
    combined.sort(key=lambda x: x[1])
    for x in filter(lambda y: y[0] != None, combined):
      print("%s\t%s" % x)


  def ansible_inventory(self, group_by, use_access_ip, groups=None):
    self.inventory = self.terraform_inventory(
                        group_by=group_by,
                        use_access_ip=use_access_ip,
                        groups=groups,
                   )
    return self.inventory


  def get_floating_ip(self, ip):
    fip = filter(
      lambda x:
        self.resources[x].primary.attributes.address == ip,
        self.get_resources(type='openstack_networking_floatingip_v2')
    )
    if fip:
      return self.resources[fip[0]].primary.attributes


  def get_instance(self, instance_id):
    ins = [ self.resources[x] for x in filter(
            lambda x:
              self.resources[x].primary.attributes.id == instance_id,
              self.get_resources(type='openstack_compute_instance_v2')
          )]
    return ins[0]


  def get_floating_ip_associations(self, instance_id):
    fips = [ self.resources[x] for x in filter(
      lambda x:
        self.resources[x].primary.attributes.instance_id == instance_id,
        self.get_resources(type='openstack_compute_floatingip_associate_v2')
    )]
    return [
      self.get_floating_ip(x.primary.attributes.floating_ip)
        for x in fips
    ]


  def get_volume(self, volid):
    vid = filter(
      lambda x:
        self.resources[x].primary.attributes.id == volid,
        self.get_resources(type='openstack_blockstorage_volume_v2')
    )
    if vid:
      res = {}
      attrs = self.resources[vid[0]].primary.attributes
      for a in attrs:
        res[str(re.sub('attachment.\d+.', '', a))] = attrs[a]
      return res


  def get_volume_attachments(self, instance_id):
    volumes = [ self.resources[x] for x in filter(
      lambda x:
        self.resources[x].primary.attributes.instance_id == instance_id,
        self.get_resources(type='openstack_compute_volume_attach_v2')
    )]
    return [
      self.get_volume(x.primary.attributes.volume_id)
        for x in volumes
    ]


  def terraform_resources(self):

    result = {}

    for key, value in [
      ('floating_ip_associations', 'openstack_compute_floatingip_associate_v2'),
      ('floating_ips',             'openstack_networking_floatingip_v2'),
      ('keypairs',                 'openstack_compute_keypair_v2'),
      ('instances',                'openstack_compute_instance_v2'),
      ('networks',                 'openstack_networking_network_v2'),
      ('router_interfaces',        'openstack_networking_router_interface_v2'),
      ('routers',                  'openstack_networking_router_v2'),
      ('security_groups',          'openstack_compute_secgroup_v2'),
      ('server_groups',            'openstack_compute_servergroup_v2'),
      ('subnets',                  'openstack_networking_subnet_v2'),
      ('volume_attachments',       'openstack_compute_volume_attach_v2'),
      ('volumes',                  'openstack_blockstorage_volume_v2')
    ]:
      try:

        resources = self.get_resources(type=value)

        if not resources or not len(resources):
          raise self.TerraformStateException('''
            No '%s' resources found or collection empty.
            Does `terraform state list | grep %s` list anything?
          ''' % (key, value))

        result[key] = {
          ( self.resources[item].primary.attributes.name if
            'name' in self.resources[item].primary.attributes else
            self.resources[item].primary.attributes.id
          ):
          { re.sub('(attachment|rule).\d+\.', '', y):
              self.resources[item].primary.attributes[y]
                for y in self.resources[item].primary.attributes
          } for item in resources
        }

      except Exception as e:
        # TODO
        # Reraising an exception here is likely desirable as we should fail if
        # the inventory requires resources we cannot find in terraform's state
        # but we would break backwards compatibility.
        warn('WARNING: Error collecting %s inventory (%s): %s' % (key, value, e))
        result[key] = {}

    return result


  def terraform_inventory(self, group_by, use_access_ip=True, groups=None):
    result = Dotable.parse({
      '_meta': {
        'hostvars': {}
      }
    })

    result['tf_resources'] = { 'hosts': [], 'vars': {} }
    result['all']          = { 'hosts': [], 'vars': {} }
    result['_meta']['hostvars']['tf_resources'] = result['tf_resources']
    result['_meta']['hostvars']['tf_resources']['vars'] = self.terraform_resources()

    hostvars = result._meta.hostvars
    for x in self.instances:
      node        = self.resources[x].primary
      instance_id = node.id
      attributes  = node.attributes
      keys        = node.attributes.keys()
      key         = attributes.name

      hostrecord = hostvars[key] = {
        x: attributes[x] for x in
          filter(lambda x: not re.search('\.', x), keys)
      }

      result['all']['hosts'].append(attributes.name)

      hostrecord['floating_ips'] = self.get_floating_ip_associations(
                                              instance_id=instance_id )

      if use_access_ip:
        hostrecord['ansible_host'] = attributes.access_ip_v4
      elif hostrecord['floating_ips']:
        hostrecord['ansible_host'] = hostrecord['floating_ips'][0].address

      # TODO
      # Is this portable into IPv6?
      if hostrecord['floating_ips']:
        hostrecord['public_ipv4']  = hostrecord['floating_ips'][0]['address']

      hostrecord['volumes'] = self.get_volume_attachments(
                                              instance_id=instance_id )

      hostrecord.update({
        x: node[x] for x in ['id', 'meta', 'tainted']
      })

      metadata = hostrecord['metadata'] = []
      metadata.append({
        re.sub('(all_)?metadata.', '', x) : attributes[x] for x in
          filter(lambda x: re.search('metadata.[^%]', x), keys)
      })

      networks = hostrecord['network'] = []
      if 'network.#' in attributes:
        for i in range(0, int(str(attributes['network.#']))):
          networks.append({
            re.sub('network.%s.' % i, '', x) : attributes[x] for x in
              filter(lambda x: re.search('network.%s' % i, x), keys)
          })

      # TODO
      # Under what conditions does terraform have more than one item
      # in the scheduler_hints lists?
      scheduler_hints = hostrecord['scheduler_hints'] = []
      if 'scheduler_hints.#' in attributes:
        for i in range(0, int(str(attributes['scheduler_hints.#']))):
          scheduler_hints.append({
            re.sub('scheduler_hints.\d+.', '', x) : attributes[x] for x in
              filter(lambda x: re.search('scheduler_hints.\d+', x), keys)
          })

      hostrecord['security_groups'] = [
        attributes[x] for x in
          filter(lambda x: re.search('security_groups.\d+', x), keys)
      ]


      # TODO server groups

      groups_node = Dotable.parse({
        'hosts': [],
        'vars': {
          'nodes': []
         }
      })

      server_groups = self.get_resources('openstack_compute_servergroup_v2')

      if not group_by and len(server_groups):
        for x in server_groups:
          name = str(self.resources[x].primary.attributes.name)
          group = result[name] = Dotable.parse( groups_node )

          attrs = self.resources[x].primary.attributes
          for y in attrs.keys():
            k = re.sub('value_specs.', '', y)
            group.vars[k] = group.vars[y] = attrs[y]

          if '%' in group['vars']:
            del group['vars']['%']

          group['vars']['nodes'] = [
            group.vars[x] for x in
            filter( lambda x: re.search('members.\d+', x), group.vars )
          ]
          group.vars['scale'] = int(group.vars['members.#'])

          group['hosts'] = [
            self.get_instance(x).primary.attributes.name
              for x in group['vars']['nodes']
          ]
      elif not group_by and not groups:
        group_by = 'name'

      if group_by:
        groupkey = attributes[group_by]
        if groupkey not in result:
          result[groupkey] = groups_node
        group = result[groupkey]
        group.hosts.append(key)
        group.vars.update({
          'scale': len(group.hosts)
        })
        result[groupkey].vars.nodes.append(instance_id)

      if groups and groups in attributes:
        for groupkey in attributes[groups].split(','):
          if groupkey not in result:
            result[groupkey] = Dotable.parse({
                'hosts': [],
                'vars': {
                  'nodes': []
                 }
              })
          group = result[groupkey]
          group.hosts.append(key)
          group.vars.update({
            'scale': len(group.hosts)
          })
          result[groupkey].vars.nodes.append(instance_id)

    return result


  def empty_inventory(self):
    return {
      '_meta': {
        'hostvars': {}
      }
    }


  def example_inventory(self):
    return {
        'tatooine': {
          'description': 'group/cluster of hosts that make up tatooine',
          'hosts': [
            'ahsoka',
            'anakin'
          ],
          'vars': {
            'description':  'group_vars that apply to all tatooines',
            'freighter':    'twilight',
            'mission':      'find shmi',
            'ansible_user': 'tatooine',
            'ansible_ssh_private_key_file': '~/.ssh/tatooine/id_rsa',
            'ansible_connection': 'ssh'
            }
          },
        'all': {
          'description': 'Special ansible group of all hosts',
          'hosts': [
            'ahsoka',
            'anakin'
          ],
          'vars': {
            'foo': 'foo is a low precedence var',
            'bar': 'is where the beers are at'
           }
        },
        '_meta': {
          'hostvars': {
            'ahsoka': {
              'description':  'host_vars for tatooine ahsoka',
              'ansible_host': '192.168.28.71',
              'status':       'master'
              },
            'anakin': {
              'description':  'host_vars for tatooine anakin',
              'ansible_host': '192.168.28.71',
              'status':       'apprentice'
              }
            }
          }
        }



def cli_args():
  parser = argparse.ArgumentParser(description='Terraform OpenStack Dynamic Inventory Script')

  parser.add_argument('--dump',    action = 'store_true',
      help='Dump the raw terraform JSON')

  parser.add_argument('--dir',     action = 'store',
      help='Dir to use for terraform state/config')

  parser.add_argument('--example', action = 'store_true',
      help='Show an example JSON inventory')

  parser.add_argument('--accessip', action='store_true',
      help='Use the instance access IP address for the value of ansible_host')

  parser.add_argument('--groupby', action='store',
      help='Instance attribute to group hosts by (default=name)')

  parser.add_argument('--groups', action='store', default='',
      help='Instance attribute with comma-separated list of groups (default=none)')

  parser.add_argument('--list',   action = 'store_true',
      help='Output entire inventory (default, implied)')

  parser.add_argument('--hosts',   action = 'store_true',
      help='Print entries for /etc/hosts')

  parser.add_argument('--file',    action = 'store',
      help='Path to file containing terraform state as JSON i.e. `terraform state pull`')

  parser.add_argument('--json',    action = 'store_true',
      help='Output inventory as JSON (faster)')

  parser.add_argument('--yaml',    action = 'store_true',
      help='Output inventory as YAML (default, slower)')

  return parser.parse_args()


if __name__ == "__main__":
  args = cli_args()

  if args.dir:
    os.chdir(args.dir)
    warn('Entering %s' % (os.getcwd()))

  if args.file:
    os.environ['TF_STATE_JSON'] = args.file

  Inventory = TerraformInventory()

  if args.list:
    args.yaml = True

  if args.example:
    print_json( Inventory.example_inventory() )

  elif args.dump:
    print_json( Inventory.data )

  elif args.hosts:
    Inventory.print_hosts_file()

  elif 'TF_HOSTS' in os.environ:
    Inventory.print_hosts_file()

  else:
    warn('Populating inventory ...')

    use_access_ip = ( os.environ['TF_USE_ACCESS_IP'] if
                'TF_USE_ACCESS_IP' in os.environ else
                args.accessip )

    group_by = ( os.environ['TF_GROUPBY'] if
                'TF_GROUPBY' in os.environ else
                args.groupby )

    groups = ( os.environ['TF_GROUPS'] if
                'TF_GROUPS' in os.environ else
                args.groups )

    if args.json or 'TF_JSON' in os.environ:
      print(
        json.dumps(
          Inventory.ansible_inventory(
            group_by=group_by,
            use_access_ip=use_access_ip,
            groups=groups,
          ),
          indent=2,
          sort_keys=True
        )
      )
    else:
      print(
        yaml.dump(
          yaml.load(
            json.dumps(
              Inventory.ansible_inventory(
                group_by=group_by,
                use_access_ip=use_access_ip,
                groups=groups,
              ),
              sort_keys=True
            )
          ),
          default_flow_style=False,
          allow_unicode=True
        )
      )

