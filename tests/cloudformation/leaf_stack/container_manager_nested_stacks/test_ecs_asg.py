
class TestEcsAsg():
    def test_ec2_permissions(self, minimal_app):
        """
        Codify the EC2 permissions, so we're flagged if they ever change.
        """
        ecs_asg_template = minimal_app.container_manager_ecs_asg_template
        # Get the name of the Cluster to check against:
        cluster_dict = ecs_asg_template.find_resources("AWS::ECS::Cluster", {})
        assert len(cluster_dict) == 1, "There should be exactly one ECS Cluster."
        cluster_id = list(cluster_dict.keys())[0]
        # Policy Definition to check the template against:
        ec2_policy_properties = {
            "PolicyDocument": {
                "Statement": [
                    {
                        "Action": [
                            "ecs:DeregisterContainerInstance",
                            "ecs:RegisterContainerInstance",
                            "ecs:Submit*"
                        ],
                        "Effect": "Allow",
                        "Resource": {
                            "Fn::GetAtt": [
                                cluster_id,
                                "Arn"
                            ]
                        }
                    },
                    {
                        "Action": [
                            "ecs:Poll",
                            "ecs:StartTelemetrySession"
                        ],
                        "Condition": {
                            "ArnEquals": {
                                "ecs:cluster": {
                                    "Fn::GetAtt": [
                                        cluster_id,
                                        "Arn"
                                    ]
                                }
                            }
                        },
                        "Effect": "Allow",
                        "Resource": "*"
                    },
                    {
                        "Action": [
                            "ecs:DiscoverPollEndpoint",
                            "ecr:GetAuthorizationToken",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        "Effect": "Allow",
                        "Resource": "*"
                    }
                ],
                "Version": "2012-10-17"
            },
        }
        ecs_asg_template.has_resource_properties(
            "AWS::IAM::Policy",
            ec2_policy_properties,
        )
