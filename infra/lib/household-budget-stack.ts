import * as path from "path";
import * as cdk from "aws-cdk-lib";
import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Construct } from "constructs";

export class HouseholdBudgetStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const table = new dynamodb.Table(this, "AppTable", {
      tableName: "household-budget-app",
      partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN
    });

    const backendLogGroup = new logs.LogGroup(this, "BackendLogGroup", {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY
    });

    const backend = new lambda.DockerImageFunction(this, "BackendFunction", {
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "../../backend"), {
        file: "Dockerfile.lambda"
      }),
      architecture: lambda.Architecture.X86_64,
      memorySize: 512,
      timeout: Duration.seconds(30),
      logGroup: backendLogGroup,
      environment: {
        DYNAMODB_TABLE_NAME: table.tableName,
        DYNAMODB_AUTO_CREATE: "false",
        SESSION_SECRET: this.node.tryGetContext("sessionSecret") || "change-me-after-deploy",
        INITIAL_USER_PASSWORD: this.node.tryGetContext("initialUserPassword") || "password",
        INITIAL_USER_1_NAME: this.node.tryGetContext("initialUser1Name") || "User 1",
        INITIAL_USER_2_NAME: this.node.tryGetContext("initialUser2Name") || "User 2"
      }
    });
    table.grantReadWriteData(backend);

    const httpApi = new apigwv2.HttpApi(this, "HttpApi", {
      apiName: "household-budget-api",
      defaultIntegration: new integrations.HttpLambdaIntegration("BackendIntegration", backend)
    });

    const siteBucket = new s3.Bucket(this, "SiteBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN
    });

    const distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultRootObject: "index.html",
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED
      },
      additionalBehaviors: {
        "/api/*": {
          origin: new origins.HttpOrigin(`${httpApi.apiId}.execute-api.${Stack.of(this).region}.${Stack.of(this).urlSuffix}`),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER
        }
      },
      errorResponses: [
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: "/index.html", ttl: Duration.minutes(1) },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: "/index.html", ttl: Duration.minutes(1) }
      ]
    });

    new s3deploy.BucketDeployment(this, "DeployFrontend", {
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ["/*"],
      sources: [
        s3deploy.Source.asset(path.join(__dirname, "../../frontend/dist-cdk"))
      ]
    });

    new CfnOutput(this, "CloudFrontUrl", {
      value: `https://${distribution.distributionDomainName}`
    });

    new CfnOutput(this, "HttpApiUrl", {
      value: httpApi.apiEndpoint
    });

    new CfnOutput(this, "DynamoDbTableName", {
      value: table.tableName
    });
  }
}
