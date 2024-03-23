SHELL:=/bin/bash
.SILENT:
.ONESHELL:
# Default action:
.DEFAULT_GOAL := cdk-deploy


## Make sure any required env-var's are set (i.e with guard-STACK_NAME)
guard-%:
	@ if [ "${${*}}" = "" ]; then \
        echo "ERROR: Required environment variable is $* not set!"; \
        exit 1; \
    fi

#########################
## Generic CDK Helpers ##
#########################

.PHONY := cdk-deploy
cdk-deploy:
	echo "Deploying Stack..." && \
	cdk deploy \
		--require-approval never \
		--no-previous-parameters \
		--all

.PHONY := cdk-synth
cdk-synth:
	echo "Synthesizing Stack..." && \
	cdk synth

.PHONY := cdk-destroy
cdk-destroy:
	echo "Destroying Stack..." && \
	cdk destroy \
		--force \
		--all

###################
## Misc Commands ##
###################

.PHONY := aws-whoami
aws-whoami:
	# Make sure you're in the right account
	aws sts get-caller-identity \
		--query Arn \
		--output text


#######################
## One Time Commands ##
#######################
.PHONY := cdk-bootstrap
cdk-bootstrap: guard-AWS_REGION guard-AWS_PROFILE
	# This needs to be run once per account/region combo
	export AWS_DEFAULT_ACCOUNT=$$(aws --region=${AWS_REGION} sts get-caller-identity --query Account --output text) && \
	echo "Running: \`cdk bootstrap aws://$${AWS_DEFAULT_ACCOUNT}/${AWS_REGION}\`..." && \
	cdk bootstrap aws://$${AWS_DEFAULT_ACCOUNT}/${AWS_REGION}
