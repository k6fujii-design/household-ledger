#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { HouseholdBudgetStack } from "../lib/household-budget-stack";

const app = new cdk.App();

new HouseholdBudgetStack(app, "HouseholdBudgetStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "ap-northeast-1"
  }
});
