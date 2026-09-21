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
- タグ定義管理、チケットへの複数タグ設定、タグ別の月次・年次・全期間集計
- ユーザーごとのAIへの注意事項の保存・参照・削除
- 月次、年次の集計
- カテゴリ別円グラフ、年次棒グラフ
- カレンダー表示
- 月次メモ、年次メモ
- 操作履歴
- LINEからのチケット登録、確認、更新、削除
- Bedrockを使った自然言語解析モード

### タグで旅行・イベント費を集計する

1. 「設定」>「タグ」で「北海道旅行」などのタグを作成します。入力欄に固定表示された`#`が先頭に付きます。
2. チケット作成・編集でタグを選択します。複数選択でき、カテゴリとは独立して保存されます。
3. 「集計」または「カレンダー」でタグを複数選択できます。選択したタグのいずれかを含むチケットが対象です。「全期間」を選べば日付や月をまたぐ費用をまとめて確認できます。カテゴリでも追加で絞れます。

過去のチケットへタグを付ける場合は、チケット一覧で対象を複数選択して「タグを一括付与」を使います。既存タグは残したまま追加されます。タグ名は設定画面の鉛筆ボタンから変更でき、IDによるチケットとの紐付けは維持されます。

未精算・精算済みのチケットを合算し、取り消し・削除済みは除外します。タグが複数付いても同じチケットを重複計上しません。各タグの集計同士には同じチケットが含まれることがあるので、タグ別総額の単純合算には注意してください。

チケット一覧でもタグで検索できます。タグの改名は既存の紐付けを維持します。使用中のタグを削除する場合は、先にチケットから外してください。既存チケットはタグなしとして動作し、移行作業は不要です。

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

`sessionSecret`はWebアプリのログインセッションCookieを署名する秘密値です。ログインパスワードとは別の値です。新しくPowerShellを開いた場合は、デプロイ前に毎回 `$sessionSecret` を定義してください。

初回は、32バイトのランダム値を生成します。生成した値はパスワードマネージャーなどの安全な場所に保管し、GitやREADMEには記載しないでください。

```powershell
$secretBytes = New-Object byte[] 32
$randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$randomGenerator.GetBytes($secretBytes)
$randomGenerator.Dispose()
$sessionSecret = [Convert]::ToBase64String($secretBytes)
```

更新デプロイでは、保管している前回と同じ値を設定します。

```powershell
$sessionSecret = "保管している前回と同じ値"
```

未定義や空文字のまま実行しないよう、デプロイ直前に確認します。この確認では秘密値そのものは表示しません。

```powershell
if ([string]::IsNullOrWhiteSpace($sessionSecret) -or $sessionSecret.Length -lt 32) {
    throw "sessionSecretが未定義、または32文字未満です。"
}
```

CDK側でも同じ検証を行うため、未指定または32文字未満の場合はデプロイを開始せずエラー終了します。

```powershell
cd ..\infra
npx.cmd cdk deploy --profile household-admin -c sessionSecret="$sessionSecret" -c lineAgentMode="rules"
```

Bedrockを使う場合は`lineAgentMode="bedrock"`を指定します。

```powershell
npx.cmd cdk deploy --profile household-admin -c sessionSecret="$sessionSecret" -c lineAgentMode="bedrock" -c bedrockModelId="amazon.nova-lite-v1:0"
```

デプロイ後、出力されるURLを確認します。

| Output | 用途 |
| --- | --- |
| `CloudFrontUrl` | WebアプリのアクセスURL |
| `HttpApiUrl` | API GatewayのURL |
| `LineWebhookUrl` | LINE Developersに設定するWebhook URL |
| `DynamoDbTableName` | DynamoDBテーブル名 |

### 更新デプロイ

**LINEでAIの要約・自然なコメントを使う場合は、更新時も必ず `-c lineAgentMode="bedrock"` と現在の `-c bedrockModelId="..."` を指定してください。** CDKは未指定の場合 `rules` になります。`rules` は生成AIを呼ばないため、件名の要約や話題に応じたコメントはできません。以下の一般手順の `rules` はルール版向けです。AI版は後述のモデルIDを入力する手順を利用してください。

Bedrockの呼び出し・JSON解析に失敗した場合は、その旨をLINEへ返し、入力をそのまま件名として登録する処理には進みません。CloudWatchの `bedrock_intent_failed` / `bedrock_intent_skipped` とLambdaの `LINE_AGENT_MODE` を確認してください。件名・コメント不足時の補完は最大1回のみで、その場合は追加のモデル呼び出し料金がかかります。負担比率は現在のスライダーと同じ10段階で扱い、合計10（100%）を保存時にも検証します。

画面変更をAWSに反映する場合も、先に`frontend/dist-cdk`を作り直してからCDKデプロイします。  
CDKデプロイでは、Lambdaコンテナイメージの更新、S3へのフロントエンド配置、CloudFrontキャッシュ削除が行われます。

新しくPowerShellを開いた場合、最初に保管済みの値を設定して検証します。更新のたびに別の値を生成すると、既存のログインセッションがすべて無効になります。

```powershell
$sessionSecret = "保管している前回と同じ値"
if ([string]::IsNullOrWhiteSpace($sessionSecret) -or $sessionSecret.Length -lt 32) {
    throw "sessionSecretが未定義、または32文字未満です。"
}

cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\frontend
Remove-Item -Recurse -Force .\dist-cdk -ErrorAction SilentlyContinue
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true

cd ..\infra
npx.cmd cdk deploy --profile household-admin -c sessionSecret="$sessionSecret" -c lineAgentMode="rules"
```

`cdk deploy`で`no changes`と表示された場合でも、`BucketDeployment`のアセット差分があればフロントエンドは更新されます。画面が古い場合は、ビルド先が`frontend/dist-cdk`になっているか確認してください。

**AIの記憶・自然言語のタグ操作を使う環境では、上のデプロイコマンドの`lineAgentMode="rules"`を`lineAgentMode="bedrock"`に変更してください。** モデルIDなどの既存の追加コンテキスト指定も引き継ぎます。今回の機能は既存DynamoDBテーブルに保存するため、新しいAWSリソースやIAM権限、手動のDB移行は不要です。ローカル更新はプロジェクト直下で`docker compose up -d --build`を実行します。

### カレンダーのタグ・LINE編集画面の更新

カレンダーの「フィルター」でタグを指定すると、日別金額・件数・月次表示合計・選択日のチケット一覧に同じ条件が適用されます。カテゴリとステータスも併用できます。「すべて」では取り消しチケットも含む従来の仕様です。

編集フォームの「LINEに戻る」リンクは、端末で動作しないため撤去しました。変更を保存した後は、LINE内ブラウザ上部の×（閉じる）で元のトークへ戻ってください。外部ブラウザの場合はLINEアプリへ切り替えます。変更後の確認メッセージをLINEに送る処理は継続しています。フォーム保存だけではチケット登録は完了せず、LINEで「登録する」を選んで確定します。過去の`lineOfficialAccountId`設定は互換性のため残っていますが、現在の編集画面では使いません。

以下をPowerShellで実行します。Docker Desktopを起動し、**前回と同じsessionSecret・モデルID・その他のカスタム設定を引き継いでください**。

```powershell
$sessionSecret = Read-Host "保管している前回と同じsessionSecretを入力" -MaskInput
if ([string]::IsNullOrWhiteSpace($sessionSecret) -or $sessionSecret.Trim().Length -lt 32) {
    throw "sessionSecretは前回と同じ32文字以上の値が必要です。"
}
$bedrockModelId = Read-Host "現在利用中のBedrockモデルID（Haiku等、推論プロファイルIDも含む）"
if ([string]::IsNullOrWhiteSpace($bedrockModelId)) { throw "現在のモデルIDを指定してください" }

cd C:\Users\srnty\OneDrive\ドキュメント\VSCode_dir\household-budget-app\frontend
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm.cmd run build -- --outDir dist-cdk --emptyOutDir true
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }

cd ..\infra
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw "infra npm ci failed" }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "infra build failed" }
$deployArgs = @("--profile", "household-admin", "-c", "sessionSecret=$sessionSecret",
    "-c", "lineAgentMode=bedrock", "-c", "bedrockModelId=$bedrockModelId")
npx.cmd cdk diff @deployArgs
if ($LASTEXITCODE -ne 0) { throw "cdk diff failed" }
if ((Read-Host "差分を確認しましたか？続行する場合は DEPLOY と入力") -ne "DEPLOY") { throw "中止しました" }
npx.cmd cdk deploy @deployArgs
if ($LASTEXITCODE -ne 0) { throw "cdk deploy failed" }
Remove-Variable sessionSecret, deployArgs
```

`Read-Host -MaskInput`はPowerShell 7.1以降用です。Windows PowerShell 5.1では、代わりに`$secretInput = Read-Host "sessionSecret" -AsSecureString`、`$sessionSecret = [System.Net.NetworkCredential]::new("", $secretInput).Password`を使えます。カスタムSSMパラメータ名等を設定している場合は、既存の`-c`指定も`$deployArgs`に追加します。`cdk diff`に意図しない変更・置換が出た場合はデプロイせず設定を確認してください。

更新後は画面を再読み込みし、タグの有無でカレンダー合計と日別一覧が一致することを確認します。LINEでは**新たに**登録候補を作って編集リンクを開き、変更保存後に画面上部の×で戻ってください。今回LIFF化はしていないため、`liff.closeWindow()`や動作を保証できない`window.close()`は使いません。SSMシークレットの変更・Webhook URLの再登録・DB移行は不要です。

ローカルではプロジェクト直下で`docker compose up -d --build`を実行します。LINE復帰のための追加ID設定は不要です。

スマートフォン実機で、保存後の確認メッセージとブラウザを閉じる動作を確認してください。

## LINE連携とAIエージェント

### できること

LINEのチャットから自然文で家計簿を操作できます。

- チケット登録
- 入力不足時の聞き返し
- 登録前確認
- 登録内容に応じた短いリアクション
- 家計簿操作以外の雑談へのフレンドリーな応答
- スマートフォン向け編集フォームによる登録候補の修正
- チケット更新
- チケット削除
- 「さっきのチケット」など直近文脈を使った操作
- 月次、年次、カテゴリ別の利用傾向の質問応答
- LINE返信は確認内容と結果のみを表示（診断ログはサーバー側に保存）

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
マリカ楽しー
今後、件名は店名を中心に短くして。覚えておいて
覚えている注意事項を教えて
件名を短くする注意事項は忘れて
北海道旅行というタグを作成して
昨日の昼食1800円、タグは北海道旅行で登録して
さっきのチケットに北海道旅行のタグを追加して
北海道旅行で全部いくら使った？
今月の北海道旅行の支出は？
タグ一覧を見せて
北海道旅行のタグ名を札幌旅行に変更して
```

チケット作成の確認メッセージには、短時間だけ利用できる編集リンクが表示されます。リンク先では、件名、日付、金額、カテゴリ、立替者、負担比率、ステータス、メモを画面操作で変更できます。カテゴリ、立替者、ステータスは選択式、日付と金額は型付き入力、負担比率はスライダーです。

変更を保存すると、LINEへ更新後の確認メッセージが届きます。内容を確認して「登録する」または「やめる」を選択してください。登録完了またはキャンセル時には会話状態と編集リンクが破棄され、次の入力は新しい会話として扱われます。

### AIの記憶とタグ操作

「設定」>「AIの記憶」で「共通」と「表示名向け」を切り替えます。「共通」は二人とも閲覧・追加・削除でき、どちらのLINE操作にも適用されます。「表示名向け」はログイン中のユーザー専用で、設定した現在の表示名を使います。既存の記憶はそのまま個人向けとして残り、移行は不要です。AIには共通と送信者本人向けの両方を渡し、競合する場合は最新の指示、本人向け、共通の順で優先するよう指示しています。

LINEでも「共通で、件名には店名を入れるように覚えて」「共通の記憶を教えて」「共通の○○という注意事項を忘れて」と指定できます。範囲の指定がなければ送信者本人向けです。

支出の短文は登録という語がなくても作成候補として扱います。例:「サミットで魚かって３０００円」。全角数字を正規化し、AIが雑談・不明と判断しても支出らしい入力は登録確認へ進みます。金額がなければ聞き返します。更新・削除・集計などの明確な指示や否定・購入前の相談を新規登録にすり替えないようにしています。登録前確認は維持します。

LINEの「処理ログ」の追記は廃止しました。`lineAgentTraceEnabled`の以前の設定値にかかわらず返信には表示しません。CloudWatchの診断ログと操作履歴は継続します。集計画面のカテゴリ・タグは「フィルター」を開いたときだけ表示し、閉じても選択条件を維持します。

`bedrock`モードでは「覚えて」「今後は〜」と明示した注意事項を保存します。「回答は簡潔にしてください」など、記憶という語がなくても継続的な振る舞いへの要望と判断した場合は保存先を示し「この方針を保存／保存しない」を提示します。保存する選択を受けてDBへ書き込み、成功後に保存完了を返します。一回のチケット修正は長期記憶にしません。相手ユーザーの個人向け記憶は参照しません。

「昨日の○○のチケットを更新したい」のような依頼は、件名キーワードと日付から最大5件の候補を表示します。番号で選択後、変更したい項目と値を伝え、更新前確認で確定します。対象チケットの条件と変更内容を別のターンで扱うため、元の日付を変更指示として誤用しません。確認中の追加修正でも選択したチケットと既存の修正内容を保持します。候補がない場合は条件を変えて検索し直してください。候補選択や方針保存のボタン処理ではモデルを再呼び出ししません。

これらは既存Lambda + Bedrock Runtime APIの改善です。AgentCoreへの移行やモデルの変更は行っていません。実モデルの意図判定には不確実性があるため、生成結果だけで確定せず、更新前確認・保存確認・入力検証を継続します。

保存済み注意事項は、次回以降のBedrockによる解析に参考情報として渡され、件名・カテゴリの判断や短いコメントの口調などに利用されます。最新の明示的な指示、認証、登録前確認、項目の型・範囲が優先されます。生成AIによる反映なので、すべての注意事項を常に厳密に遵守する保証はありません。集計結果など定型の返信はプログラム側で生成します。

記憶は共通30件、各ユーザーの個人向け30件、1件500文字まで。3分の会話タイムアウトや登録完了・キャンセルでは消えず、明示的に削除するまで残ります。パスワードやAPIトークンは記憶に登録しないでください。記憶はBedrockへの入力に含まれるため、保存量に応じて入力トークン量が増えます。診断ログの`agent_preferences_loaded`には利用した記憶IDを記録し、本文は通常ログに出しません（メッセージ全文ログを有効にした場合は入力・応答に含まれ得ます）。

LINEからタグ定義の作成・一覧・改名・未使用タグの削除、チケットへの付与・解除、タグ集計ができます。知らないタグ名が指定されたら先に作成を促します。編集フォームでもタグを複数選択できます。期間指定のないタグ集計は全期間、期間指定があればその範囲が対象です。`rules`モードでの自然文の記憶管理・タグ定義操作は対象外です。Web画面の機能はどちらのモードでも使えます。

保存先は既存DynamoDBテーブルの`TAG`（タグ定義）、`AGENT_MEMORY_SHARED`（共通の注意事項）、`AGENT_MEMORY#<アプリユーザーID>`（個人向け注意事項）です。チケットの`tag_ids`で定義に紐付けます。実装は`backend/app/services/agent_preferences.py`、解析ルールはUTF-8の`backend/app/prompts/line_agent_intent.txt`、管理APIは`backend/app/routers/settings.py`です。追加のAWSリソースやIAM権限は不要ですが、フロントエンドのビルドとバックエンドの再デプロイの両方が必要です。現在のモデルIDとsessionSecretを引き継いでください。

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
$sessionSecret = "保管している前回と同じ値"
npx.cmd cdk deploy --profile household-admin -c sessionSecret="$sessionSecret"
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

### LINE AI処理の診断ログを確認する

LINEからのチケット操作は、LambdaのCloudWatch LogsへJSON形式の診断ログを出力します。同じ会話は`conversation_id`、同じWebhookイベントは`request_id`で追跡できます。

主なイベントは次のとおりです。

| イベント | 内容 |
| --- | --- |
| `line_agent_message_started` | LINE入力の受付と現在の会話状態 |
| `bedrock_intent_completed` | Bedrockが抽出した意図と項目、トークン使用量 |
| `line_agent_create_candidate_created` | 最初に作成した登録候補 |
| `line_agent_create_candidate_merged` | 修正前、修正指定、変更項目、修正後、値の抽出元 |
| `line_agent_session_saved` | 確認待ち会話の保存 |
| `line_agent_tool_executed` | チケット作成・更新・削除などの実行結果 |
| `bedrock_intent_failed` / `line_reply_failed` | Bedrock解析またはLINE返信の失敗 |

既定ではLINE本文を保存せず、文字数とSHA-256ハッシュだけを記録します。問題調査中だけ本文とBedrockの生出力を記録する場合は、CDKデプロイに次のコンテキストを追加します。

```powershell
npx.cmd cdk deploy --profile household-admin `
  -c sessionSecret="$sessionSecret" `
  -c lineAgentDiagnosticLogging=true `
  -c lineAgentLogMessageText=true
```

調査後は`lineAgentLogMessageText=false`で再デプロイしてください。診断ログ全体を止める場合は`lineAgentDiagnosticLogging=false`を指定します。

ロググループ名は次のコマンドで確認できます。

```powershell
aws cloudformation describe-stack-resources `
  --profile household-admin `
  --region ap-northeast-1 `
  --stack-name HouseholdBudgetStack `
  --logical-resource-id BackendLogGroup
```

取得したロググループ名を指定してリアルタイム表示します。

```powershell
aws logs tail "ロググループ名" `
  --profile household-admin `
  --region ap-northeast-1 `
  --since 1h `
  --follow
```

CloudWatch Logsの保持期間はCDKで1週間に設定しています。LINE Channel secret、アクセストークン、完全なLINEユーザーIDはログへ出力しません。

## ライセンス

未設定です。公開範囲や利用目的に応じて、必要であれば後から追加してください。
