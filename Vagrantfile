#-*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
# General Vagrant VM
  config.vm.box = "ubuntu/trusty64"
  config.ssh.insert_key = false
  config.vm.provider :virtualbox do | v |
    v.memory = 2048
  end

# docnow server
  config.vm.define "docnow" do | docnow |
    docnow.vm.hostname = "docnow-app1.dev"
    docnow.vm.network :private_network, ip: "192.168.60.14"
    docnow.vm.provision "ansible_local" do |ansible|
        ansible.playbook = "./provision/site.yml"
        ansible.sudo = true
    end
  end

# redis server
  config.vm.define "redis" do | redis |
    redis.vm.hostname = "redis-app1.dev"
    redis.vm.network :private_network, ip: "192.168.60.15"
    redis.vm.provision "ansible_local" do |ansible|
        ansible.playbook = "./provision/redis.yml"
        ansible.sudo = true
    end
  end
end
