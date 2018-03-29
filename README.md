# tofu

A terraform openstack dynamic inventory script that parses the output
of `terraform state pull` to generate a YAML or JSON blurb that can
be read in by ansible to use as a dynamic inventory.

## Usage

```
$ bin/tf-os-ansible-inventory.py --help
usage: tf-os-ansible-inventory.py [-h] [--dump] [--dir DIR] [--example] [--groupby GROUPBY] [--hosts] [--file FILE] [--json] [--yaml]

Terraform Dynamic Inventory

optional arguments:
  -h, --help         show this help message and exit
  --dump             Dump the raw terraform JSON
  --dir DIR          Dir to use for terraform state/config
  --example          Show an example JSON inventory
  --groupby GROUPBY  Instance attribute to group hosts by (default=name)
  --hosts            Print entries for /etc/hosts
  --file FILE        Path to file containing terraform state as JSON i.e. `terraform state pull`
  --json             Output inventory as JSON (faster)
  --yaml             Output inventory as YAML (default, slower)
```

The basic use-case is to have ansible execute `tofu`

```
$ cat ansible.cfg

[defaults]
inventory = bin/tofu.py
 ```

```
chmod +x bin/tofu.py

terraform plan
terraform apply
terraform state pull | python -m json.tool # Just to know what the deal is
ansible-playbook ./site.yml -l webserver-0[1:6]
```

### Grouping

As is often the case, the above is no good as infrastructure is composed of
logical groups of instances where you need to run different plays against
different groups. For this scenario, you can use `--groupby` to collate
terraform resource instances into groups grouped by some instance attribute
that terraform holds in its state.

e.g. consider a typical object representation of an instance (
See `terraform state pull` for the complete picture) and assume that
there are other instances sharing similar attributes

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
> ansible invokes to call the above.

If you use [Server Groups]
(https://www.terraform.io/docs/providers/openstack/r/compute_servergroup_v2.html)
to describe your server groups/affinity/anti-affinity policies then `tofu` will
use the server groups to collate instances. This is useful in that it is
probably what you need and it avoids the need for a wrapper script.

