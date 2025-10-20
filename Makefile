# Respect pathing
export PWD=$(dir $(realpath $(firstword $(MAKEFILE_LIST))))
SHELL:=/bin/bash
.SILENT:
MAKEFLAGS += --no-print-directory
# Default action:
.DEFAULT_GOAL := cdk-synth

### Figure out the application variables:
#    Do here instead of the cdk app, so they're not duplicated in both and
#    avoid getting out of sync. Just pass them in
maturity ?= prod
# The _application_id and _base_stack_name are only here to have in one place,
#    THEY'RE NOT MEANT TO BE MODIFIED DIRECTLY, except through the 'maturity' var:
ifeq ($(maturity),prod)
	_application_id := "ContainerManager"
else
	_application_id := "ContainerManager-$(maturity)"
endif
_base_stack_name := "$(_application_id)-BaseStack"

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
	echo ""
	cdk deploy "$(stack-regix)" \
		--require-approval never \
		--no-previous-parameters \
	    --context _application_id="$(_application_id)" \
		--context _base_stack_name="$(_base_stack_name)" \
		--context config-file="$(config-file)" \
		--context maturity="$(maturity)" \
		--context container-id="$(container-id)"
	echo "Finished at: `date +'%-I:%M%P (%Ss)'`"

# Edit the base stack:
.PHONY := cdk-deploy-base
cdk-deploy-base:
	$(MAKE) _cdk-deploy-helper stack-regix="$(_base_stack_name)"

# Edit everything BUT the base stack, within the config-file scope:
#  (The base stack will still be updated as a 'Dependency Stack')
.PHONY := cdk-deploy-leaf
cdk-deploy-leaf: guard-config-file
	echo "Config File: $(config-file)"
	$(MAKE) _cdk-deploy-helper stack-regix="!$(_base_stack_name)"



###################
#### DESTROY STUFF:
.PHONY := _cdk-destroy-helper
_cdk-destroy-helper: guard-stack-regix # empty config-file is okay here
	echo "Destroying Stack..."
	echo "Starting at: `date +'%-I:%M%P (%Ss)'`"
	echo ""
	cdk destroy "$(stack-regix)" \
		--force \
	    --context _application_id="$(_application_id)" \
		--context _base_stack_name="$(_base_stack_name)" \
		--context config-file="$(config-file)" \
		--context maturity="$(maturity)" \
		--context container-id="$(container-id)"
	echo "Finished at: `date +'%-I:%M%P (%Ss)'`"

# Destroy the base stack
.PHONY := cdk-destroy-base
cdk-destroy-base:
	$(MAKE) _cdk-destroy-helper stack-regix="$(_base_stack_name)"

# Destroy everything BUT the base stack, within the config-file scope:
#  (The base stack will still be updated as a 'Dependency Stack')
.PHONY := cdk-destroy-leaf
cdk-destroy-leaf: guard-config-file
	echo "Config File: $(config-file)"
	$(MAKE) _cdk-destroy-helper stack-regix="!$(_base_stack_name)"


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
		echo "Config File: $(config-file)"; \
	else \
		echo "No Config File"; \
		echo "    (Pass in with 'make cdk-synth config-file=<config>' to synth that stack too!)"; \
	fi
	echo "Synthesizing Stack..."
	echo ""
	cdk synth \
	    --context _application_id="$(_application_id)" \
		--context _base_stack_name="$(_base_stack_name)" \
		--context config-file="$(config-file)" \
		--context maturity="$(maturity)" \
		--context container-id="$(container-id)" \
		$(STACKS)

.PHONY := lint-python
lint-python:
	pylint $$(git ls-files '*.py')

.PHONY := lint-markdown
lint-markdown:
	node --run lint:markdown

###################
## Misc Commands ##
###################

.PHONY := test
test:
	tox run

.PHONY := aws-whoami
aws-whoami:
	# Make sure you're in the right account
	aws sts get-caller-identity \
		--query "$${query:-Arn}" \
		--output text

.PHONY := update-npm-lint
# Installs locally:
update-npm-lint:
	echo "## Updating NPM Lint Stuff..."
	npm install --save-dev \
		markdownlint-cli2@latest \
		markdownlint-rule-relative-links@latest
	echo ""

.PHONY := update-npm-cdk
# Installs globally:
update-npm-cdk:
	echo "## Setting up non-root Install..."
	mkdir -p ~/.npm-global
	npm config set prefix '~/.npm-global'
	echo "## Updating NPM CDK Stuff..."
	npm install --global \
		npm@latest \
		aws-cdk@latest
	echo ""

.PHONY := update-python
update-python:
	echo "Updating Python Stuff..."
	python3 -m pip install --upgrade \
		pip \
		-r requirements.txt \
		-r requirements-dev.txt
	echo ""

.PHONY := update
update: update-npm-cdk update-npm-lint update-python

.PHONY := cdk-bootstrap
# --app="": CDK can't synth without the right variables, so don't load the app:
cdk-bootstrap:
	echo "Bootstrapping/Updating CDKToolkit..." && \
	export AWS_ACCOUNT_ID=$$( $(MAKE) aws-whoami query=Account ) && \
	cdk bootstrap \
		--app="" \
		"aws://$${AWS_ACCOUNT_ID}/$$( aws configure get region )" \
		"aws://$${AWS_ACCOUNT_ID}/us-east-1"
