SHELL:=/bin/bash
.SILENT:
.ONESHELL:
MAKEFLAGS += --no-print-directory
# Default action:
.DEFAULT_GOAL := cdk-synth

### NOTE: IF THIS IS CHANGED: Also change it in the Makefile:
base_stack_name := "ContainerManager-BaseStack"
maturity := "prod"

## Make sure any required env-var's are set (i.e with guard-STACK_NAME)
guard-%:
	@ if [ "${${*}}" = "" ]; then \
        echo "ERROR: Required variable '$*' is not set!"; \
		echo "    (either export it, or use 'make <target> $*=abc')"; \
        exit -1; \
    fi

#########################
## Generic CDK Helpers ##
#########################

##################
#### DEPLOY STUFF:
.PHONY := _cdk-deploy-helper
_cdk-deploy-helper: guard-stack-regix # empty config-file is okay here
	echo "Deploying Stack..."
	echo "Starting at: `date +'%-I:%M%P (%Ss)'`"
	base_stack_name=asdf
	echo "$(base_stack_name)"
	# cdk deploy "$(stack-regix)" \
	# 	--require-approval never \
	# 	--no-previous-parameters \
	# 	--context config-file="$(config-file)" \
	# 	--context maturity="$(maturity)"
	#   --context stack_name="TODO"
	echo "Finished at: `date +'%-I:%M%P (%Ss)'`"

# Edit the base stack:
.PHONY := cdk-deploy-base
cdk-deploy-base:
	$(MAKE) _cdk-deploy-helper stack-regix="$(base_stack_name)" config-file=""

# Edit everything BUT the base stack (within the config-file scope):
.PHONY := cdk-deploy-leaf
cdk-deploy-leaf: guard-config-file
	echo "Config File: $(config-file)"
	$(MAKE) _cdk-deploy-helper stack-regix="!$(base_stack_name)" config-file="$(config-file)"



###################
#### DESTROY STUFF:
.PHONY := _cdk-destroy-helper
_cdk-destroy-helper: guard-stack-regix # empty config-file is okay here
	echo "Destroying Stack..."
	echo "Starting at: `date +'%-I:%M%P (%Ss)'`"
	echo ""
	cdk destroy "$(stack-regix)" \
		--force \
		--context config-file="$(config-file)"
	echo "Finished at: `date +'%-I:%M%P (%Ss)'`"

# Destroy the base stack
.PHONY := cdk-destroy-base
cdk-destroy-base:
	base_stack_name=`python3 -c "import app; print(app.base_stack_name)"`
	$(MAKE) _cdk-destroy-helper stack-regix="$${base_stack_name}" config-file=""

# Destroy the leaf stack inside the config-file
.PHONY := cdk-destroy-leaf
cdk-destroy-leaf: guard-config-file
	echo "Config File: $(config-file)"
	base_stack_name=`python3 -c "import app; print(app.base_stack_name)"`
	$(MAKE) _cdk-destroy-helper stack-regix="!$${base_stack_name}" config-file="$(config-file)"


########################
#### SYNTH / LINT STUFF:
## Take all non-var input, remove the 'cdk-synth' beginning, and pass the rest to cdk synth as stack-names
##    (Can do stuff like `make cdk-synth --config-file=./my-config.yaml stack2` to ONLY synth stack2)
# If the first argument is "cdk-synth"...
ifeq (cdk-synth,$(firstword $(MAKECMDGOALS)))
  # use the rest as arguments for "cdk-synth"
  STACKS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # ...and turn them into do-nothing targets
  $(eval $(STACKS):;@:)
endif
.PHONY := cdk-synth
cdk-synth:
	if [[ -n "$(config-file)" ]]; then \
		echo "Config File: $(config-file)";
	else \
		echo "No Config File";
		echo "    (Pass in with 'make cdk-synth config-file=<config>' to synth that stack too!)";
	fi
	echo "Synthesizing Stack..."
	echo ""
	cdk synth --context config-file="$(config-file)" $(STACKS)

.PHONY := pylint
pylint:
	pylint $$(git ls-files '*.py')

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
