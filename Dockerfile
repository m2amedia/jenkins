# https://hub.docker.com/r/jenkins/jenkins/tags/
FROM jenkins/jenkins:2.125

ENV TERRAFORM_VERSION=0.11.7

USER root

RUN apt-get update && apt-get install -y bash git wget openssh-server vim gettext make docker awscli ruby python-pip htop

# Install pip
ADD requirements.txt /root/requirements.txt
RUN pip install -r /root/requirements.txt

# Download terraform binary
RUN cd /tmp && \
    wget https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/cache/apk/* && \
    rm -rf /var/tmp/*

RUN terraform -v

# Allow the jenkins user to run docker
RUN groupadd docker
RUN usermod -aG docker jenkins

# Scripts
ADD scripts /usr/share/jenkins/scripts
RUN chown -R jenkins:jenkins /usr/share/jenkins/scripts
RUN chmod +x /usr/share/jenkins/scripts
RUN chmod +x /usr/share/jenkins/scripts/*
ENV PATH="/usr/share/jenkins/scripts:${PATH}"

# Drop back to the regular jenkins user
USER jenkins

# 1. Disable Jenkins setup Wizard UI. The initial user and password will be supplied by Terraform via ENV vars during infrastructure creation
# 2. Set Java DNS TTL to 60 seconds
# http://docs.aws.amazon.com/sdk-for-java/v1/developer-guide/java-dg-jvm-ttl.html
# http://docs.oracle.com/javase/7/docs/technotes/guides/net/properties.html
# https://aws.amazon.com/articles/4035
# https://stackoverflow.com/questions/29579589/whats-the-recommended-way-to-set-networkaddress-cache-ttl-in-elastic-beanstalk
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Dhudson.DNSMultiCast.disabled=true -Djava.awt.headless=true -Dsun.net.inetaddr.ttl=60 -Duser.timezone=PST -Dorg.jenkinsci.plugins.gitclient.Git.timeOut=60"

# Preinstall plugins
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN /usr/local/bin/install-plugins.sh < /usr/share/jenkins/ref/plugins.txt

# Setup Jenkins initial admin user, security mode (Matrix), and the number of job executors
# Many other Jenkins configurations could be done from the Groovy script
COPY init.groovy /usr/share/jenkins/ref/init.groovy.d/

# Configure `Amazon EC2` plugin to start slaves on demand
COPY init-ec2.groovy /usr/share/jenkins/ref/init.groovy.d/

EXPOSE 8080