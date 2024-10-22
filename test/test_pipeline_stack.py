# Copyright Amazon.com and its affiliates; all rights reserved. This file is Amazon Web Services Content and may not be duplicated or distributed without permission.
# SPDX-License-Identifier: MIT-0
from test.boto_mocking_helper import *

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

import lib.configuration as configuration
from lib.configuration import (
    ACCOUNT_ID,
    DEV,
    GITHUB_REPOSITORY_NAME,
    GITHUB_REPOSITORY_OWNER_NAME,
    GLUE_VERSION,
    LINEAGE,
    LOGICAL_ID_PREFIX,
    PROD,
    REGION,
    RESOURCE_NAME_PREFIX,
    SPARK_WORKER_TYPE,
    TEST,
)
from lib.stacks.pipeline_stack import PipelineStack

mock_configuration_base = {
    ACCOUNT_ID: mock_account_id,
    REGION: mock_region,
    # Mix Deploy environment variables so we can return one dict for all environments
    LOGICAL_ID_PREFIX: 'TestLake',
    RESOURCE_NAME_PREFIX: 'testlake',
    LINEAGE: True,
    GLUE_VERSION: '4.0',
    SPARK_WORKER_TYPE: 'G.1X',
}

def mock_get_local_configuration_with_github(environment, local_mapping = None):
    return mock_configuration_base | \
        {
            GITHUB_REPOSITORY_NAME: 'mock-github-repository',
            GITHUB_REPOSITORY_OWNER_NAME: 'hernandj',
        }

# def mock_get_local_configuration_with_codestar(environment, local_mapping = None):
#     return mock_configuration_base | \
#         {
#             CODECOMMIT_MIRROR_REPOSITORY_NAME: '',
#             GITHUB_REPOSITORY_NAME: '',
#             CODESTAR_REPOSITORY_NAME: 'mock-codestar-repository',
#             CODESTAR_REPOSITORY_OWNER_NAME: 'test-owner',
#             CODESTAR_CONNECTION_ARN: 'arn:aws:codestar-connections:::',
#         }


# def test_resource_types_and_counts(monkeypatch):
#     monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)
#     monkeypatch.setattr(configuration, 'get_local_configuration', mock_get_local_configuration_with_codecommit)

#     app = cdk.App()

#     pipeline_stacks = {}
#     for environment in [DEV, TEST, PROD]:
#         pipeline_stacks[environment] = PipelineStack(
#             app,
#             f'{environment}-PipelineStackForTests',
#             target_environment=environment,
#             target_branch='main',
#             # Target and Pipeline account/region are the same - not testing cross-account/cross-region
#             target_aws_env={ 'account': mock_account_id, 'region': mock_region },
#             env=cdk.Environment(
#                 account=mock_account_id,
#                 region=mock_region
#             ),
#         )

#     # 3 stacks expected (dev, test, prod), no cross-pipeline support stack
#     assert len(app.node.children) == 3, 'Unexpected number of stacks'

#     # All stacks should be generated before calling Template methods
#     for environment in pipeline_stacks.keys():
#         template = Template.from_stack(pipeline_stacks[environment])

#         template.resource_count_is('AWS::CodePipeline::Pipeline', 1)
#         # Project for cdk synth, and pipeline update/self-mutate, 6 file asset pipeline steps
#         template.resource_count_is('AWS::CodeBuild::Project', 8)
#         # Artifact bucket
#         template.resource_count_is('AWS::S3::Bucket', 1)
#         # Artifact bucket encryption key
#         template.resource_count_is('AWS::KMS::Key', 1)
#         # LogGroup for each build action (includes 6 file asset pipeline steps)
#         template.resource_count_is('AWS::Logs::LogGroup', 8)
#         # CodePipeline role, 3 CodeBuild roles, 2 Pipeline action roles, Pipeline event role
#         template.resource_count_is('AWS::IAM::Role', 7)


def test_cross_region_number_of_stacks(monkeypatch):
    monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)

    app = cdk.App()

    pipeline_stacks = {}
    for environment in [DEV, TEST, PROD]:
        pipeline_stacks[environment] = PipelineStack(
            app,
            f'{environment}-PipelineStackForTests',
            target_environment=environment,
            target_branch='main',
            # Different fake region for each environment to trigger pipeline support stack
            target_aws_env={
                'account': mock_account_id,
                'region': f'{environment.lower()}-region'
            },
            env=cdk.Environment(
                account=mock_account_id,
                region=mock_region
            ),
        )

    # 3 infrastructure stacks (dev, test, prod), 3 pipeline support stacks
    assert len(app.node.children) == 6, 'Unexpected number of stacks' # 6 stacks total


def test_cross_account_number_of_stacks(monkeypatch):
    monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)

    app = cdk.App()

    pipeline_stacks = {}
    for environment in [DEV, TEST, PROD]:
        pipeline_stacks[environment] = PipelineStack(
            app,
            f'{environment}-PipelineStackForTests',
            target_environment=environment,
            target_branch='main',
            # Different accounts for each environment
            target_aws_env={
                'account': f'{environment.lower()}notrealaccount',
                'region': mock_region
            },
            env=cdk.Environment(
                account=mock_account_id,
                region=mock_region
            ),
        )

    # 3 stacks expected (dev, test, prod)
    assert len(app.node.children) == 3, 'Unexpected number of stacks'


def test_pipeline_self_mutates(monkeypatch):
    monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)

    app = cdk.App()

    stack_logical_id = 'Dev-PipelineStackForTests'
    pipeline_stack = PipelineStack(
        app,
        stack_logical_id,
        target_environment=DEV,
        target_branch='main',
        target_aws_env={ 'account': mock_account_id, 'region': mock_region },
        env=cdk.Environment(
            account=mock_account_id,
            region=mock_region
        ),
    )

    template = Template.from_stack(pipeline_stack)
    template.has_resource_properties(
        'AWS::CodeBuild::Project',
        Match.object_like(
            {
                "Source": {
                    "BuildSpec": Match.serialized_json(
                        {
                            "version": Match.any_value(),
                            "phases": {
                                "install": Match.any_value(),
                                "build": {
                                    "commands": [
                                        Match.string_like_regexp(fr'cdk -a . deploy {stack_logical_id} \S+')
                                    ]
                                }
                            }
                        }
                    )
                }
            }
        )
    )


def test_codebuild_runs_synth(monkeypatch):
    monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)

    app = cdk.App()

    pipeline_stack = PipelineStack(
        app,
        'Dev-PipelineStackForTests',
        target_environment=DEV,
        target_branch='main',
        target_aws_env={ 'account': mock_account_id, 'region': mock_region },
        env=cdk.Environment(
            account=mock_account_id,
            region=mock_region
        ),
    )

    template = Template.from_stack(pipeline_stack)
    template.has_resource_properties(
        'AWS::CodeBuild::Project',
        Match.object_like(
            {
                "Source": {
                    "BuildSpec": Match.serialized_json(
                        {
                            "version": Match.any_value(),
                            "phases": {
                                "build": {
                                    "commands": Match.array_with(['cdk synth'])
                                }
                            },
                            "artifacts": Match.any_value()
                        }
                    )
                }
            }
        )
    )


# def test_pipeline_pulls_source_from_connection(monkeypatch):
#     monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)
#     monkeypatch.setattr(configuration, 'get_local_configuration', mock_get_local_configuration_with_codestar)

#     app = cdk.App()

#     pipeline_stack = PipelineStack(
#         app,
#         'Dev-PipelineStackForTests',
#         target_environment=DEV,
#         target_branch='main',
#         # Target and Pipeline account/region are the same - not testing cross-account/cross-region
#         target_aws_env={ 'account': mock_account_id, 'region': mock_region },
#         env=cdk.Environment(
#             account=mock_account_id,
#             region=mock_region
#         ),
#     )

#     template = Template.from_stack(pipeline_stack)
#     template.has_resource_properties(
#         'AWS::CodePipeline::Pipeline',
#         Match.object_like(
#             {
#                 "Stages": Match.array_with([
#                     {
#                         "Actions": [
#                             {
#                                 "ActionTypeId": {
#                                     "Category": "Source",
#                                     "Owner": "AWS",
#                                     "Provider": "CodeStarSourceConnection",
#                                     "Version": "1"
#                                 },
#                                 "Configuration": Match.any_value(),
#                                 "Name": Match.any_value(),
#                                 "OutputArtifacts": Match.any_value(),
#                                 "RoleArn": Match.any_value(),
#                                 "RunOrder": 1,
#                             },
#                         ],
#                         "Name": "Source",
#                     }
#                 ])
#             }
#         )
#     )


def test_pipeline_pulls_source_from_github(monkeypatch):
    monkeypatch.setattr(configuration.boto3, 'client', mock_boto3_client)
    monkeypatch.setattr(configuration, 'get_local_configuration', mock_get_local_configuration_with_github)

    app = cdk.App()

    pipeline_stack = PipelineStack(
        app,
        'Dev-PipelineStackForTests',
        target_environment=DEV,
        target_branch='main',
        # Target and Pipeline account/region are the same - not testing cross-account/cross-region
        target_aws_env={ 'account': mock_account_id, 'region': mock_region },
        env=cdk.Environment(
            account=mock_account_id,
            region=mock_region
        ),
    )

    template = Template.from_stack(pipeline_stack)
    template.has_resource_properties(
        'AWS::CodePipeline::Pipeline',
        Match.object_like(
            {
                "PipelineType": "V2",
                "ExecutionMode": "QUEUED",
                "Stages": Match.array_with([
                    {
                        "Actions": [
                            {
                                "ActionTypeId": {
                                    "Category": "Source",
                                    "Owner": "AWS",
                                    "Provider": "CodeStarSourceConnection",
                                    "Version": "1"
                                },
                                "Configuration": Match.any_value(),
                                "Name": Match.any_value(),
                                "OutputArtifacts": Match.any_value(),
                                "RoleArn": Match.any_value(),
                                "RunOrder": 1,
                            },
                        ],
                        "Name": "Source",
                    }
                ])
            }
        )
    )