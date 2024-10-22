# Copyright Amazon.com and its affiliates; all rights reserved. This file is Amazon Web Services Content and may not be duplicated or distributed without permission.
# SPDX-License-Identifier: MIT-0
from test.boto_mocking_helper import *

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

import lib.configuration as configuration
from lib.configuration import (
    ACCOUNT_ID,
    DEV,
    GLUE_VERSION,
    LINEAGE,
    LOGICAL_ID_PREFIX,
    PROD,
    REGION,
    RESOURCE_NAME_PREFIX,
    SPARK_WORKER_TYPE,
    TEST,
    VPC_CIDR,
)
from lib.stacks.dynamodb_stack import DynamoDbStack
from lib.stacks.glue_stack import GlueStack


def mock_get_local_configuration_with_vpc(environment, local_mapping = None):
	return {
		ACCOUNT_ID: mock_account_id,
		REGION: mock_region,
		LINEAGE: False,
		# Mix Deploy environment variables so we can return one dict for all environments
		LOGICAL_ID_PREFIX: 'TestLake',
		RESOURCE_NAME_PREFIX: 'testlake',
		VPC_CIDR: '10.0.0.0/24',
        GLUE_VERSION: '4.0',
        SPARK_WORKER_TYPE: 'G.1X',
	}


def test_resource_types_and_counts(monkeypatch):
	monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)

	app = cdk.App()

	# Use one DynamoDbStack stack for all 3 environments since it is not the test subject
	dynamodb_stack = DynamoDbStack(
		app,
		'DynamoDbStackForTests',
		target_environment=DEV
	)

	glue_stacks = {}
	for environment in [DEV, TEST, PROD]:
		glue_stacks[environment] = GlueStack(
			app,
			f'{environment}-GlueStackForTests',
			target_environment=environment,
			hash_values_table=dynamodb_stack.hash_values_table,
			value_lookup_table=dynamodb_stack.value_lookup_table,
			multi_lookup_table=dynamodb_stack.value_lookup_table,
			dq_results_table=dynamodb_stack.dq_results_table,
		)

	# All stacks should be generated before calling Template methods
	for environment in glue_stacks.keys():
		template = Template.from_stack(glue_stacks[environment])

		# Collect-Cleanse, Cleanse-Consume
		template.resource_count_is('AWS::Glue::Job', 3)
		# Glue Scripts, Glue Temp
		template.resource_count_is('AWS::S3::Bucket', 2)
		# S3 Deployment CustomResource handler, CustomResource Log Retention handler
		template.resource_count_is('AWS::Lambda::Function', 2)
		# Glue Job role, S3 Deployment CustomResource handler role, CustomResource Log Retention handler role
		template.resource_count_is('AWS::IAM::Role', 3)


def test_glue_connections_with_vpc(monkeypatch):
	monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)
	monkeypatch.setattr(configuration, 'get_local_configuration', mock_get_local_configuration_with_vpc)

	app = cdk.App()

	# Use one DynamoDbStack stack for all 3 environments since it is not the test subject
	dynamodb_stack = DynamoDbStack(
		app,
		'DynamoDbStackForTests',
		target_environment=DEV
	)

	glue_stack = GlueStack(
		app,
		'Dev-GlueStackForTests',
		target_environment=DEV,
		hash_values_table=dynamodb_stack.hash_values_table,
		value_lookup_table=dynamodb_stack.value_lookup_table,
		multi_lookup_table=dynamodb_stack.value_lookup_table,
		dq_results_table=dynamodb_stack.dq_results_table,
	)
	template = Template.from_stack(glue_stack)

	# 3 Glue Connections, one for each AZ
	template.resource_count_is('AWS::Glue::Connection', 3)