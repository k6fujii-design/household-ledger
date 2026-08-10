# Household Ledger

スマートフォンのブラウザから使う、2人用の共有型家計簿Webアプリです。  
日々の支払いをチケットとして登録し、負担比率にもとづいて「誰が誰にいくら精算するか」を確認できます。

## 目次

- [画面イメージ](#画面イメージ)
- [アプリ概要](#アプリ概要)
- [主な機能](#主な機能)
- [AWS構成](#aws構成)
- [ソフトウェアスタック](#ソフトウェアスタック)
- [ディレクトリ構成](#ディレクトリ構成)
- [ローカル実行](#ローカル実行)
- [AWSデプロイ](#awsデプロイ)
- [LINE連携とAIエージェント](#line連携とaiエージェント)
- [CDKの中で定義していること](#cdkの中で定義していること)
- [セキュリティとGit管理対象](#セキュリティとgit管理対象)
- [トラブルシュート](#トラブルシュート)

## 画面イメージ

<div align="center">
  <table>
    <tr>
      <td align="center" valign="top" width="19%">
        <img src="docs/screens/ss-home.jpg" alt="ホーム画面" width="185"><br>
        <sub>ホーム</sub>
      </td>
      <td align="center" valign="top" width="19%">
        <img src="docs/screens/ss-home2.jpg" alt="ホーム画面の明細" width="185"><br>
        <sub>ホーム明細</sub>
      </td>
      <td align="center" valign="top" width="19%">
        <img src="docs/screens/ss-ticket.jpg" alt="チケット一覧画面" width="185"><br>
        <sub>チケット</sub>
      </td>
      <td align="center" valign="top" width="19%">
        <img src="docs/screens/ss-summary.jpg" alt="集計画面" width="185"><br>
        <sub>集計</sub>
      </td>
      <td align="center" valign="top" width="19%">
        <img src="docs/screens/ss-calender.png" alt="カレンダー画面" width="185"><br>
        <sub>カレンダー</sub>
      </td>
    </tr>
  </table>
</div>

## アプリ概要

Household Ledgerは、同居・家族・パートナー間の立替精算をシンプルに管理するための家計簿アプリです。

ローカル開発ではDocker ComposeとDynamoDB Localを使います。AWS環境ではCloudFront、S3、API Gateway、Lambda、DynamoDBを使い、ALBや常時起動サーバーを持たない低コストなサーバレス構成で動作します。

## 主な機能

- 2ユーザー用ログイン
- チケットの作成、参照、編集、複製、削除
- 未精算、精算済み、取り消しのステータス管理
- 支払者と負担比率にもとづく精算額の自動計算
- ホーム画面での月次精算状況、未精算額、精算済み額の確認
- チケット一覧でのステータス、カテゴリ、日付、金額順検索
- カテゴリ管理、テンプレート管理、締め日設定
- 月次、年次の集計
- カテゴリ別円グラフ、年次棒グラフ
- カレンダー表示
- 月次メモ、年次メモ
- 操作履歴
- LINEからのチケット登録、確認、更新、削除
- Bedrockを使った自然言語解析モード

## AWS構成

![AWS構成図](docs/aws-architecture.svg)

### AWSリソース

| リソース | 用途 |
| --- | --- |
| CloudFront | Webアプリの公開URL。S3の静的ファイルを配信します。 |
| S3 | React/Viteでビルドしたフロントエンドを配置します。バケットは非公開です。 |
| API Gateway HTTP API | フロントエンドとLINE WebhookからのAPIリクエストをLambdaへ転送します。 |
| Lambda | FastAPIバックエンドをDockerイメージとして実行します。 |
| DynamoDB | チケット、設定、履歴、LINEセッションなどのアプリデータを保存します。 |
| SSM Parameter Store | 初期パスワード、LINE Channel secret、LINE Channel access tokenをSecureStringで管理します。 |
| CloudWatch Logs | Lambdaのログを保存します。 |
| ECR/CDK Assets | Lambda用Dockerイメージのアップロード先としてCDKが利用します。 |
| IAM | LambdaからDynamoDB、SSM、Bedrockへアクセスする権限を定義します。 |

### 通信経路

```text
スマートフォン / ブラウザ
  |
  v
CloudFront
  |-- /*      -> S3 private bucket
  |-- /api/*  -> API Gateway HTTP API -> Lambda -> DynamoDB / SSM / Bedrock

LINE Messaging API
  |
  v
API Gateway HTTP API /line/webhook -> Lambda -> DynamoDB / SSM / Bedrock
```

## ソフトウェアスタック

### フロントエンド

- React
- TypeScript
- Vite
- lucide-react
- CSS

### バックエンド

- Python 3.12
- FastAPI
- Mangum
- boto3
- DynamoDB

### インフラ

- AWS CDK v2
- TypeScript
- Docker image Lambda
- CloudFront / S3 / API Gateway / DynamoDB / SSM Parameter Store

## ディレクトリ構成

```text
household-budget-app/
  backend/              FastAPIバックエンド
  frontend/             React/Viteフロントエンド
  infra/                AWS CDKによるインフラ定義
  docs/                 README用画像、AWS構成図など
  docker-compose.yml    ローカル実行用Docker Compose
  .env.example          ローカル環境変数のサンプル
  .gitignore            Git管理対象外ファイルの定義
  README.md             このドキュメント
```

### `backend/`

APIサーバー本体です。ローカルでは通常のFastAPIサーバーとして動作し、AWSではMangumを介してLambda上で動作します。

```text
backend/
  app/
    main.py             FastAPIアプリ本体、ルーター登録、Lambdaハンドラー
    store.py            DynamoDBアクセス層
    core/               設定、認証、シークレット取得、ログ設定
    routers/            auth、tickets、reports、calendar、users、line_webhookなどのAPI
    schemas/            API入出力の型定義
    services/           LINE連携、AI解析、操作ログなどの処理
  Dockerfile            ローカル開発用コンテナ
  Dockerfile.lambda     AWS Lambda用コンテナイメージ
  requirements.txt      Python依存関係
```

### `frontend/`

ブラウザで動く画面側の実装です。Viteでビルドした成果物を、ローカルでは開発サーバー、AWSではS3とCloudFrontで配信します。

```text
frontend/
  index.html
  package.json
  src/
    main.tsx            Reactアプリの起点
    api/                バックエンドAPIクライアント
    components/         共通UI部品
    pages/              ホーム、チケット、集計、記録、カレンダー、設定など
    styles/             アプリ全体のCSS
    types.ts            フロントエンドの型定義
```

### `infra/`

AWSへ自動構築するためのCDK定義です。アプリ本体ではなく、AWSリソースを作るためのコードです。

```text
infra/
  bin/household-budget.ts             CDKアプリの起点
  lib/household-budget-stack.ts       AWSリソース定義の中心
  cdk.json                            CDK実行設定
  package.json                        CDK依存関係
```

### `docker-compose.yml`

ローカル動作確認用のリソース定義です。AWSデプロイ用ではありません。

- `frontend`: Vite開発サーバー
- `backend`: FastAPIバックエンド
- `dynamodb`: DynamoDB Local

## ローカル実行

### 前提

- Docker Desktop
- Node.js / npm
- Git

### 起動

PowerShellでリポジトリ直下に移動して実行します。

```powershell
cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app
docker compose up --build
```

起動後、以下にアクセスします。

| 用途 | URL |
| --- | --- |
| フロントエンド | http://localhost:3000 |
| バックエンドAPI | http://localhost:8000 |
| DynamoDB Local | http://localhost:8001 |

### 初期ログイン

| ユーザー | メールアドレス |
| --- | --- |
| User 1 | `f@example.com` |
| User 2 | `o@example.com` |

ローカル初期パスワードは、環境変数未指定の場合は`password`です。

## AWSデプロイ

### 前提

- AWSアカウント
- AdministratorAccess相当の権限を持つIAMユーザー、またはCDKデプロイに必要な権限を持つIAMロール
- AWS CLI
- Node.js / npm
- Docker Desktop
- CDK bootstrap済み、または初回にbootstrapを実行できること

Lambdaはコンテナイメージとしてデプロイされます。そのため、デプロイ時にはローカルPCでDocker Desktopが起動しており、PowerShellからDockerにアクセスできる必要があります。  
AWS上でLambdaが実行されるときに、ローカルPCのDocker Desktopが必要になるわけではありません。

### PowerShellとLinux/macOSの違い

このREADMEのコマンド例はWindows PowerShell向けです。Linux/macOSからもデプロイできますが、削除コマンドやパス表記は置き換えてください。

| 操作 | PowerShell | Linux/macOS |
| --- | --- | --- |
| ディレクトリ削除 | `Remove-Item -Recurse -Force .\dist-cdk` | `rm -rf dist-cdk` |
| npm実行 | `npm.cmd run build` | `npm run build` |
| CDK実行 | `npx.cmd cdk deploy` | `npx cdk deploy` |

### 1. AWS CLIプロファイル確認

例では`household-admin`というAWS CLIプロファイルを使います。

```powershell
aws sts get-caller-identity --profile household-admin
```

### 2. CDK依存関係のインストール

```powershell
cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\infra
npm install
```

### 3. 初回のみCDK bootstrap

```powershell
npx.cmd cdk bootstrap --profile household-admin
```

### 4. SSM Parameter Storeへシークレットを登録

GitHubへ公開するため、パスワードやLINEトークンはコードに埋め込まず、SSM Parameter StoreのSecureStringで管理します。

```powershell
$initialUserPassword = "任意の初期ログインパスワード"
$lineChannelSecret = "LINE Channel secret"
$lineChannelAccessToken = "LINE Channel access token"

aws ssm put-parameter --profile household-admin --region ap-northeast-1 --name "/household-ledger/initial-user-password" --type SecureString --value "$initialUserPassword" --overwrite

aws ssm put-parameter --profile household-admin --region ap-northeast-1 --name "/household-ledger/line/channel-secret" --type SecureString --value "$lineChannelSecret" --overwrite

aws ssm put-parameter --profile household-admin --region ap-northeast-1 --name "/household-ledger/line/channel-access-token" --type SecureString --value "$lineChannelAccessToken" --overwrite
```

### 5. フロントエンドをCDK配信用にビルド

必ず`frontend`ディレクトリで実行します。リポジトリ直下や`infra`配下で`vite build`を実行すると、`index.html`が見つからず失敗します。

```powershell
cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\frontend
Remove-Item -Recurse -Force .\dist-cdk -ErrorAction SilentlyContinue
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true
```

### 6. CDKデプロイ

```powershell
cd ..\infra
npx.cmd cdk deploy --profile household-admin -c sessionSecret="十分に長いランダム文字列" -c lineAgentMode="rules"
```

Bedrockを使う場合は`lineAgentMode="bedrock"`を指定します。

```powershell
npx.cmd cdk deploy --profile household-admin -c sessionSecret="十分に長いランダム文字列" -c lineAgentMode="bedrock" -c bedrockModelId="amazon.nova-lite-v1:0"
```

デプロイ後、出力されるURLを確認します。

| Output | 用途 |
| --- | --- |
| `CloudFrontUrl` | WebアプリのアクセスURL |
| `HttpApiUrl` | API GatewayのURL |
| `LineWebhookUrl` | LINE Developersに設定するWebhook URL |
| `DynamoDbTableName` | DynamoDBテーブル名 |

### 更新デプロイ

画面変更をAWSに反映する場合も、先に`frontend/dist-cdk`を作り直してからCDKデプロイします。  
CDKデプロイでは、Lambdaコンテナイメージの更新、S3へのフロントエンド配置、CloudFrontキャッシュ削除が行われます。

```powershell
cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\frontend
Remove-Item -Recurse -Force .\dist-cdk -ErrorAction SilentlyContinue
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true

cd ..\infra
npx.cmd cdk deploy --profile household-admin -c sessionSecret="前回と同じ値" -c lineAgentMode="rules"
```

`cdk deploy`で`no changes`と表示された場合でも、`BucketDeployment`のアセット差分があればフロントエンドは更新されます。画面が古い場合は、ビルド先が`frontend/dist-cdk`になっているか確認してください。

## LINE連携とAIエージェント

### できること

LINEのチャットから自然文で家計簿を操作できます。

- チケット登録
- 入力不足時の聞き返し
- 登録前確認
- チケット更新
- チケット削除
- 「さっきのチケット」など直近文脈を使った操作
- 月次、年次、カテゴリ別の利用傾向の質問応答
- AIがどのように解釈したかの処理ログ表示

### 必要なもの

- LINE公式アカウント
- Messaging API Channel
- Channel secret
- Channel access token
- Webhook URL設定
- アプリ側へのLINEユーザーID登録

### LINE Developers側の設定

1. LINE DevelopersでMessaging API Channelを作成します。
2. Channel secretとChannel access tokenをSSM Parameter Storeへ登録します。
3. CDKデプロイ後に出力される`LineWebhookUrl`をWebhook URLとして登録します。
4. Webhookの利用を有効化します。
5. 応答メッセージなど、LINE公式アカウント側の不要な自動応答は必要に応じて無効化します。

### LINEユーザーIDの登録

LINEの`source.userId`は、同じMessaging API Channel内でユーザーごとに異なるIDです。  
アプリの「設定」>「ユーザー設定」から、User 1、User 2それぞれのLINEユーザーIDを登録します。

未登録ユーザーがBotにメッセージを送ると、アプリは「このLINEユーザーIDは家計簿アプリに登録されていません」と返信し、確認用のユーザーIDを返します。

### AIモード

| モード | 説明 | コスト |
| --- | --- | --- |
| `rules` | ルールベースで金額、日付、カテゴリなどを解析します。Bedrockは使いません。 | 低い |
| `bedrock` | Bedrockで意図判定、件名整形、登録、更新、削除、集計質問を解析します。 | 利用量に応じて発生 |

### LINE入力例

```text
昨日スーパーで3200円、食費で入れといて
登録する
今月の利用金額教えて
先月と比べてどう？
今年なにが一番多い？
チケットID 10 金額3500円に変更
チケットID 10 削除
さっきのチケット消して
```

### ツールとして想定している処理

AIエージェントは、自然文を解釈して次のようなアプリ操作へ変換します。

| ツール | 用途 |
| --- | --- |
| `create_ticket` | チケット作成 |
| `update_ticket` | チケット更新 |
| `delete_ticket` | チケット削除 |
| `search_tickets` | チケット検索 |
| `answer_summary` | 月次、年次、カテゴリ傾向の回答 |
| `ask_missing_amount` | 金額など必須項目が不足している場合の聞き返し |

## CDKの中で定義していること

CDKの中心は`infra/lib/household-budget-stack.ts`です。

### `infra/bin/household-budget.ts`

CDKアプリの起動ファイルです。`HouseholdBudgetStack`を生成し、`cdk deploy`時にこのスタックが評価されます。

### `infra/lib/household-budget-stack.ts`

AWSリソースを定義しています。

- DynamoDBテーブルを作成
- Lambda用CloudWatch Log Groupを作成
- SSM Parameter Storeのパラメータ名を定義
- FastAPIバックエンドをLambda Docker imageとして定義
- LambdaへDynamoDB、SSM、BedrockのIAM権限を付与
- API Gateway HTTP APIを作成
- S3バケットを作成
- CloudFront Distributionを作成
- `frontend/dist-cdk`をS3へアップロード
- CloudFrontキャッシュを無効化
- デプロイ後に必要なURLやテーブル名をOutputとして表示

## セキュリティとGit管理対象

### GitHubへ上げないもの

`.gitignore`で以下をGit管理対象外にしています。

| パス | 理由 |
| --- | --- |
| `frontend/node_modules/` | npm依存関係。再インストール可能です。 |
| `frontend/dist/` | フロントエンドのビルド成果物です。 |
| `frontend/dist-*/` | 検証用、AWS用などのビルド成果物です。 |
| `infra/node_modules/` | CDKのnpm依存関係です。 |
| `infra/cdk.out/` | CDKの合成結果です。 |
| `infra/cdk.context.json` | CDKの環境依存キャッシュです。 |
| `backend/.venv/` | Python仮想環境です。 |
| `backend/__pycache__/` | Pythonキャッシュです。 |
| `backend/app/**/__pycache__/` | Pythonキャッシュです。 |
| `.pytest_cache/` | pytestのキャッシュです。 |

### シークレット管理

以下はコードやREADMEに実値を記載しないでください。

- AWS access key
- AWS secret access key
- LINE Channel secret
- LINE Channel access token
- 本番ログインパスワード
- `sessionSecret`

AWS環境では、ログイン初期パスワードとLINE関連シークレットはSSM Parameter StoreのSecureStringで管理します。

## コストの考え方

アクセス頻度が低い場合、主なコスト要素は以下です。

- CloudFrontのリクエストとデータ転送
- S3の保存容量とリクエスト
- API Gateway HTTP APIのリクエスト
- Lambdaの実行時間
- DynamoDBのオンデマンド読み書き
- Bedrock利用時のモデル呼び出し

1日1回程度の利用であれば、Bedrockを多用しない限りかなり小さなコストで運用しやすい構成です。

## 削除

AWSリソースを削除する場合は以下を実行します。

```powershell
cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\infra
npx.cmd cdk destroy --profile household-admin
```

DynamoDBテーブルとS3バケットはデータ保護のため`RETAIN`にしているため、必要に応じてAWSコンソールから手動削除してください。

## トラブルシュート

### `Cannot resolve entry module index.html`

`vite build`を`frontend`以外のディレクトリで実行している可能性があります。必ず`frontend`へ移動してから実行してください。

```powershell
cd household-budget-app\frontend
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true
```

### Docker daemonに接続できない

LambdaをDockerイメージとしてビルドするため、CDKデプロイ時にDockerへアクセスできる必要があります。

- Docker Desktopを起動する
- PowerShellを開き直す
- `docker version`で接続できるか確認する
- Windowsで`Access is denied`になる場合は、ユーザーを`docker-users`グループへ追加してサインアウト、サインインする
- 必要に応じてPowerShellを管理者として実行する

### 画面更新がAWSに反映されない

`frontend/dist-cdk`が更新されていない可能性があります。再ビルドしてからCDKデプロイしてください。

```powershell
cd household-budget-app\frontend
Remove-Item -Recurse -Force .\dist-cdk -ErrorAction SilentlyContinue
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true

cd ..\infra
npx.cmd cdk deploy --profile household-admin -c sessionSecret="前回と同じ値"
```

### LINEで「このLINEユーザーIDは登録されていません」と表示される

返信に表示されたLINEユーザーIDを、Webアプリの「設定」>「ユーザー設定」に登録してください。  
LINEユーザーIDはMessaging API Channel内でユーザーごとに発行されるIDです。

### LINEメッセージに既読だけ付いて返信がない

以下を確認してください。

- LINE DevelopersのWebhook URLが`LineWebhookUrl`になっている
- Webhookの利用が有効
- Channel secretとChannel access tokenがSSM Parameter Storeに登録されている
- CDKデプロイ後のLambda環境変数が正しいSSMパラメータ名を参照している
- CloudWatch LogsにLambdaエラーが出ていない

## ライセンス

未設定です。公開範囲や利用目的に応じて、必要であれば後から追加してください。
