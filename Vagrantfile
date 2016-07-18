#-*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.provider :virtualbox do |vb|
    vb.customize ["modifyvm", :id, "--memory", "4096"]
  end

# hydra server

  config.vm.define "docnowvm" do |docnowvm|
    docnowvm.vm.hostname = "docnowvm"
    docnowvm.vm.box = "ubuntu/trusty64"
    docnowvm.vm.network :private_network, ip: "192.168.60.144"
    config.ssh.insert_key = false
  end

# Ansible provision

  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "provision/provision.yml"
  end
end
