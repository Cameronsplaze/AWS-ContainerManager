SHELL:=/bin/bash
.SILENT:
.ONESHELL:
# Default action:
.DEFAULT_GOAL := cdk-deploy
# Force these to be commands, NOT files:
.PHONY := cdk-deploy cdk-synth cdk-bootstrap


## Make sure any required env-var's are set (i.e with guard-STACK_NAME)
guard-%:
	@ if [ "${${*}}" = "" ]; then \
        echo "ERROR: Required environment variable is $* not set!"; \
        exit 1; \
    fi

#####################
## Generic Helpers ##
#####################
cdk-deploy:
	echo "Deploying Stack..." && \
	cdk deploy \
		--require-approval never \
		--no-previous-parameters \
		--all \
		--profile cs-personal

cdk-synth:
	echo "Synthesizing Stack..." && \
	cdk synth \
		--profile cs-personal

cdk-destroy:
	echo "Destroying Stack..." && \
	cdk destroy \
		--force

#######################
## One Time Commands ##
#######################
cdk-bootstrap: guard-AWS_REGION
	# This needs to be run once per account/region
	if [ -z "${AWS_DEFAULT_PROFILE}" ]; then echo "WARNING: AWS_DEFAULT_PROFILE is not set"; fi && \
	export AWS_DEFAULT_ACCOUNT=$$(aws --region=${AWS_REGION} sts get-caller-identity --query Account --output text) && \
	echo "Running: \`cdk bootstrap aws://$${AWS_DEFAULT_ACCOUNT}/${AWS_REGION}\`..." && \
	cdk bootstrap aws://$${AWS_DEFAULT_ACCOUNT}/${AWS_REGION}
