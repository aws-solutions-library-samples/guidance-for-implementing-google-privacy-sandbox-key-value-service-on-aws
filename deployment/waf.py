# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This creates a AWS WAFv2 ACL resource with managed rules 
from aws_cdk import (
    Stack,
    aws_wafv2 as wafv2,
)
from constructs import Construct


class Waf(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        managed_rules = [
            {
                "name": "AWSManagedRulesCommonRuleSet",
                "priority": 10,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesAmazonIpReputationList",
                "priority": 20,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesKnownBadInputsRuleSet",
                "priority": 30,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesSQLiRuleSet",
                "priority": 40,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesLinuxRuleSet",
                "priority": 50,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesUnixRuleSet",
                "priority": 60,
                "override_action": "none",
                "excluded_rules": [],
            },
        ]

        wafacl = wafv2.CfnWebACL(
            self,
            id="WAF",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow=wafv2.CfnWebACL.AllowActionProperty(), block=None
            ),
            scope="REGIONAL",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="waf-regional",
                sampled_requests_enabled=True,
            ),
            description="WAFv2 ACL for Regional",
            name="waf-regional",
            rules=self.waf_rules(managed_rules),
        )

        wafv2.CfnWebACLAssociation(
            self,
            "collectionwafassociation",
            resource_arn=self.node.try_get_context("alb-arn"),
            web_acl_arn=wafacl.attr_arn,
        )

    def waf_rules(self, list_of_rules={}):
        rules = list()
        for r in list_of_rules:
            rule = wafv2.CfnWebACL.RuleProperty(
                name=r["name"],
                priority=r["priority"],
                override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        name=r["name"], vendor_name="AWS", excluded_rules=[]
                    )
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=r["name"],
                    sampled_requests_enabled=True,
                ),
            )
            rules.append(rule)

        rule_geo_match = wafv2.CfnWebACL.RuleProperty(
            name="GeoMatch",
            priority=0,
            action=wafv2.CfnWebACL.RuleActionProperty(
                block={}  ## To disable, change to *count*
            ),
            statement=wafv2.CfnWebACL.StatementProperty(
                not_statement=wafv2.CfnWebACL.NotStatementProperty(
                    statement=wafv2.CfnWebACL.StatementProperty(
                        geo_match_statement=wafv2.CfnWebACL.GeoMatchStatementProperty(
                            country_codes=[
                                "VE",
                                "KP",
                            ]
                        )
                    )
                )
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="GeoMatch",
                sampled_requests_enabled=True,
            ),
        )
        rules.append(rule_geo_match)

        rule_limit_requests_100 = wafv2.CfnWebACL.RuleProperty(
            name="LimitRequests100",
            priority=1,
            action=wafv2.CfnWebACL.RuleActionProperty(block={}),
            statement=wafv2.CfnWebACL.StatementProperty(
                rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                    limit=100, aggregate_key_type="IP"
                )
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="LimitRequests100",
                sampled_requests_enabled=True,
            ),
        )
        rules.append(rule_limit_requests_100)

        rule_chrome_user_agent = wafv2.CfnWebACL.RuleProperty(
            name="ChromeUserAgent",
            priority=100,
            action=wafv2.CfnWebACL.RuleActionProperty(block={}),
            statement=wafv2.CfnWebACL.StatementProperty(
                byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                    field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                        single_header={"name": "user-agent"}
                    ),
                    positional_constraint="CONTAINS",
                    search_string="Chrome",
                    text_transformations=[
                        wafv2.CfnWebACL.TextTransformationProperty(
                            priority=0,
                            type="NONE",
                        )
                    ],
                )
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="ChromeUserAgent",
                sampled_requests_enabled=True,
            ),
        )
        rules.append(rule_chrome_user_agent)

        return rules
