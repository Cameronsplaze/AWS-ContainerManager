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
	echo "Config File: $(config-file)" && \
	cdk deploy \
		--require-approval never \
		--no-previous-parameters \
		--all \
		--context config-file="$(config-file)"

.PHONY := cdk-synth
cdk-synth:
	echo "Synthesizing Stack..." && \
	echo "Config File: $(config-file)" && \
	cdk synth --context config-file="$(config-file)"

.PHONY := cdk-destroy-all
cdk-destroy-all:
	echo "Destroying Stack..." && \
	echo "Config File: $(config-file)" && \
	cdk destroy \
		--force \
		--all \
		--context config-file="$(config-file)"

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
	cdk bootstrap "aws://$${AWS_DEFAULT_ACCOUNT}/${AWS_REGION}" && \
	echo "Required in us-east-1 for domain_stack too, running there now..." && \
	cdk bootstrap "aws://$${AWS_DEFAULT_ACCOUNT}/us-east-1" && \
	echo "DONE!"
