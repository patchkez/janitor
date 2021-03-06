#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import glanceclient.v2.client as glclient
from os import getenv
from novaclient.client import Client
from keystoneauth1.identity import v2
from keystoneauth1 import session
from neutronclient.v2_0.client import Client as neutronclient
from sys import exit


class Credentials(object):
    def __init__(self, openrc=None):
        self.openrc_path = openrc
        self.osp_username = getenv("OS_USERNAME")
        self.osp_password = getenv("OS_PASSWORD")
        self.osp_tenant = getenv("OS_TENANT_NAME")
        self.osp_auth_url = getenv("OS_AUTH_URL")
        self.osp_auth_version = '3.x_password'
        self.osp_service_type = 'compute'
        self.osp_service_region = getenv("OS_REGION_NAME")

        # file overrides env variable
        if self.openrc_path:
            openrc = self.read_openrc()
            self.osp_username = openrc["OS_USERNAME"]
            self.osp_password = openrc["OS_PASSWORD"]
            self.osp_tenant = openrc["OS_TENANT_NAME"]
            self.osp_auth_url = openrc["OS_AUTH_URL"]
            self.osp_service_region = openrc["OS_REGION_NAME"]

        if not self.osp_username:
            raise Exception("Missing OS_USERNAME")

        if not self.osp_password:
            raise Exception("Missing OS_PASSWORD")

        if not self.osp_tenant:
            raise Exception("Missing OS_TENANT_NAME")

        if not self.osp_auth_url:
            raise Exception("Missing OS_AUTH_URL")

        if not self.osp_service_region:
            raise Exception("Missing OS_REGION_NAME")

    def read_openrc(self):
        openrc = {}
        with open(self.openrc_path) as fdata:
            lines = fdata.readlines()
            for line in lines:
                if line.startswith('export'):
                    # string formating
                    kv = line.replace("export", "").replace("\"", "").\
                        strip().split("=")
                    if "/v2.0" in kv[1]:
                        kv[1] = kv[1].replace("/v2.0", "")
                    openrc[kv[0]] = kv[1]
            return openrc


class OpenstackSDK(object):
    def __init__(self, openrc=None):
        self.creds = Credentials(openrc)
        self.auth = v2.Password(auth_url="%s/%s"
                                % (self.creds.osp_auth_url, "/v2.0"),
                                username=self.creds.osp_username,
                                password=self.creds.osp_password,
                                tenant_name=self.creds.osp_tenant)
        self.session = session.Session(auth=self.auth)
        self.nova = Client('2', session=self.session)
        self.glance = glclient.Client('2', session=self.session)
        self.neutron = neutronclient(session=self.session)

    def get_all_instances(self):
        try:
            rs = self.nova.servers.list()
            vm_list = []
            for vm in rs:
                name = None
                image = None
                created_at = None
                flavor = None
                vm_id = None

                if "id" in vm.image:
                    # situation when image is deleted but there are vms
                    # with that image associated. e.g.: vm1 is provisioned
                    # with image1 then image1 is deleted from tenant
                    # or from public
                    try:
                        os_img = self.glance.images.get(vm.image['id'])
                        image = os_img['name']
                    except Exception as ex:
                        print ex
                        image = "NA, prev deleted"

                if vm.name and vm.name is not None:
                    name = vm.name

                if vm.created and vm.created is not None:
                    created_at = vm.created

                if vm.flavor and "id" in vm.flavor is not None:
                    flavor = vm.flavor['id']

                if vm.id and vm.id is not None:
                    vm_id = vm.id

                instance = {'name': name,
                            'image': image,
                            'created_at': created_at,
                            'flavor': flavor,
                            'ips': ', '.join(self.get_server_ips(vm)),
                            'id': vm_id,
                            'obj': vm
                            }
                vm_list.append(instance)
        except Exception as ex:
            # for troubleshooting
            print ex
            if vm:
                print "WARN: check this vm %s" % vm
            raise(ex)
        return vm_list

    def delete_instance(self, vm):
        """delete openstack instance"""
        try:
            self.nova.servers.delete(vm['obj'])
            return True
        except Exception as ex:
            print ex

    def get_server_ips(self, server):
        """get IPs for a given server object"""
        server_ips = []
        for key, value in server.addresses.iteritems():
            for elem in value:
                server_ips.append(elem['addr'])
        return server_ips

    def get_zoombies_floating_ips(self):
        """get all floating ips and filter by disassociated ips"""
        all_floating_ips = self.neutron.list_floatingips()
        zoombies = []
        for fip in all_floating_ips['floatingips']:
            if not fip['port_id'] and not fip['router_id']:
                zoombies.append(fip)
        return zoombies

    def delete_floating_ip(self, ip):
        """delete openstack instance"""
        try:
            self.neutron.delete_floatingip(ip)
            return True
        except Exception as ex:
            print ex
