# tofu

A TerraForm OpenStack dynamic inventory script that parses the JSON object
from `terraform state pull` to generate a YAML or JSON blurb that is suitable
for an ansible dynamic inventory.

This approach is slightly different to the official
[OpenStack dynamic inventory script](http://docs.ansible.com/ansible/2.5/user_guide/intro_dynamic_inventory.html#example-openstack-external-inventory-script)
that queries the OpenStack APIs to compose the inventory. The advantage with
`tofu` is it aims to use the TerraForm state independently of the OpenStack state
to do the same and with no other python library dependencies
(e.g. [Shade](https://pypi.python.org/pypi/shade))

## Requirements

* Python 2.x
* TerraForm

## Usage

```
$ tofu.py --help
usage: tofu.py [-h] [--dump] [--dir DIR] [--example] [--groupby GROUPBY] [--hosts] [--file FILE] [--json] [--yaml]

Terraform OpenStack Dynamic Inventory Script

optional arguments:
  -h, --help         show this help message and exit
  --dump             Dump the raw terraform JSON
  --dir DIR          Dir to use for terraform state/config
  --example          Show an example JSON inventory
  --accessip         Use the instance access IP address for the value of
                     ansible_host
  --groupby GROUPBY  Instance attribute to group hosts by (default=name)
  --groups GROUPS    Instance attribute with comma-separated list of groups
                     (default=none)
  --list             Output entire inventory (default, implied)
  --hosts            Print entries for /etc/hosts
  --file FILE        Path to file containing terraform state as JSON i.e.
                     `terraform state pull`
  --json             Output inventory as JSON (faster)
  --yaml             Output inventory as YAML (default, slower)

```

The basic use-case is to have ansible execute `tofu` to return a YAML/JSON
object to use as a
[dynamic inventory](http://docs.ansible.com/ansible/latest/user_guide/intro_dynamic_inventory.html)

```
chmod +x tofu.py
ansible -i tofu.py -u ubuntu AZ1-BER-NORTH -m ping
```

Or for a less in-your-face integration ..

```
$ cat ansible.cfg

[defaults]
inventory = bin/tofu.py
 ```

```
chmod +x bin/tofu.py

terraform plan
terraform apply
ansible-playbook ./site.yml -l webserver-0[1:6]
```

### Grouping

As is often the case, the above is no good as infrastructure is composed of
logical groups of instances where you need to run different plays against
different groups. To support this, you can use `--groupby` to collate
terraform resource instances into groups grouped by some instance attribute
that terraform holds in its state.

e.g. consider the typical object representation of an instance in
terraform's state (See `terraform state pull` for a complete JSON object)
and assume there are other instances sharing similar attributes that can
be used as the key to do the grouping.

```
nginx-01:
  ...
nginx-02:
  access_ip_v4: 172.28.216.195
  access_ip_v6: ''
  all_metadata.%: '9'
  all_metadata.availability_zone: AZ1
  all_metadata.cluster: reverse-proxy
  all_metadata.datacenter: AZ1-BER-NORTH
  all_metadata.description: nginx-member
  all_metadata.external_network: floating-ip-network
  all_metadata.flavor_name: m1.medium
  all_metadata.owner: apportune
  all_metadata.tags: reverse-proxy,proxy,nginx
  all_metadata.tier: app
  availability_zone: AZ1
  flavor_id: '3'
  flavor_name: m1.medium
  force_delete: 'false'
  id: fbc114e3-2bf4-4948-9379-892991e9ac3c
  image_id: 2d1e80fb-2207-48b1-9184-ca9a3645102b
  image_name: xenial
  key_pair: apportune-ansible-keypair
  metadata.%: '9'
  metadata.availability_zone: AZ1
  metadata.cluster: reverse-proxy
  metadata.datacenter: AZ1-BER-NORTH
  metadata.description: reverse-proxy member
  metadata.external_network: floating-ip-network
  metadata.flavor_name: m1.medium
  metadata.owner: apportune
  metadata.tags: reverse-proxy,load-balancer,proxy,nginx
  metadata.tier: app
  name: nginx-02
  network.#: '1'
  network.0.access_network: 'false'
  network.0.fixed_ip_v4: 172.28.216.195
  network.0.fixed_ip_v6: ''
  network.0.floating_ip: ''
  network.0.mac: fa:16:3e:ad:21:fd
  network.0.name: home-net
  network.0.port: ''
  network.0.uuid: 8697f9f1-5a24-4a86-aed5-d5214d8ebec7
  region: RegionOne
  scheduler_hints.#: '1'
  scheduler_hints.3495812989.additional_properties.%: '0'
  scheduler_hints.3495812989.build_near_host_ip: ''
  scheduler_hints.3495812989.different_host.#: '0'
  scheduler_hints.3495812989.group: 3cf5de1a-9976-42d6-8166-10eab28b2582
  scheduler_hints.3495812989.query.#: '0'
  scheduler_hints.3495812989.same_host.#: '0'
  scheduler_hints.3495812989.target_cell: ''
  security_groups.#: '6'
  security_groups.1268873843: mgmt-ha-in
  security_groups.1379193405: ssh-in
  security_groups.2240927461: web-in
  security_groups.3115836137: check-mk-in
  security_groups.3682986736: nrpe-in
  security_groups.3814588639: default
  stop_before_destroy: 'false'
  user_data: 326307df82495cebcc95f6cdc5abbea55c634a3c
nginx-03
      ...
```

then

```
tofu.py --groupby metadata.cluster # uses the metadata.cluster attribute
                                   # of the instances to do the grouping

tofu.py --groupby network.0.name   # Will group instances by their placement
                                   # on their default/home networks

tofu.py --groupby availability_zone # group by AZ

tofu.py --groupby image_id         # Group by isntances sharing the same
                                   # deployment image?

tofu.py --groupby name             # Useful? Creates groups of size 1

...
```

> NOTE: You will need a wrapper script that becomes the executable that
> ansible invokes to call `tofu` to do grouping this way.

If you use
[Server Groups](https://www.terraform.io/docs/providers/openstack/r/compute_servergroup_v2.html)
in terraform to describe groups or affinity/anti-affinity policies then `tofu`
will use the servergroup name as the grouping key. This is useful in that it is
probably what you need and is a logical fit for `tofu` and so avoids the need
for a wrapper script.

Grouping can also be done in a
[static fashion](http://docs.ansible.com/ansible/latest/user_guide/intro_dynamic_inventory.html#static-groups-of-dynamic-groups)

To do grouping similar to Ansible Openstack inventory plugin, i.e. use a
comma-separated list of groups from metadata.groups attribute, you would use
`--groups=metadata.groups`.

### Generating /etc/hosts entries

    tofu.py --hosts

### Working with multiple terraform projects/directories

    tofu.py --dir terraform/AZ1-BER-NORTH/ > AZ1-BER_NORTH.json
    tofu.py --dir terraform/AZ1-MUN-SOUTH/ > AZ1-MUN-SOUTH.json

    /path/to/json-merge-tool AZ1-BER-NORTH.json AZ1-MUN-SOUTH.json

Where `json-merge-tool` is some tool that merges the 2/many JSON files and
returns that as the dynamic inventory to `ansible`.

## Controlling the IP address used for ansible_host

By default, `tofu` will use the value of the instances' first floating IP
address in the inventory to allow direct ansible/SSH access into the instances.

If this is not desired or if ansible is able to connect directly via ssh into
the instances, the `--accessip` flag dictates that `tofu` use the instance
private/access IP address instead.

## Troubleshooting

`tofu` runs `terraform state ...`, so you will need to ensure it is run in
the same directory that `terraform` runs.

    terraform state pull > tf-state.json # Ensure this file is populated first

    tofu.py --file tf-state.json --json | python -m json.tool

    tofu.py --file tf-state.json --dump

## TODO

* Implement caching and `--refresh` semantics to speed up the dev cycle.
* Support using hostnames or FQDNs for the value of `ansible_host` in
  the inventory where using IP addresses may not be desirable.
* Honour the `--host` argument for the inventory of a single host.
* Change `--hosts` to mean the plural of `--host`, consider a better
  argument to replace `--hosts` as we have now.
