# Google Cloud SDK セットアップ - ステップバイステップ

このガイドに従って、Google Cloud SDK をインストール→認証→デプロイを完了してください。

---

## ステップ 1: PowerShell を開く

1. Windows キー + R を押す
2. `powershell` と入力して Enter を押す
3. **管理者として実行** してください（右クリック → 管理者として実行）

---

## ステップ 2: Scoop インストール（gcloud のパッケージマネージャー）

PowerShell で以下をコピペして実行：

```powershell
iwr -useb get.scoop.sh | iex
```

実行例：
```
> iwr -useb get.scoop.sh | iex
Initializing...
...
Scoop was installed successfully!
```

---

## ステップ 3: Google Cloud SDK をインストール

同じ PowerShell で以下を実行：

```powershell
scoop install gcloud
```

実行例：
```
> scoop install gcloud
Installing 'gcloud' (XYZ.X.X) [64bit]
...
'gcloud' (XYZ.X.X) was installed successfully!
```

インストール完了後、**PowerShell を閉じてから新しく開いてください**（パスの更新のため）

---

## ステップ 4: gcloud が正しくインストールされたか確認

新しい PowerShell を開いて実行：

```powershell
gcloud --version
```

出力例：
```
Google Cloud SDK XYZ.X.X
...
```

**この表示が出たら OK です！** ✓

---

## ステップ 5: Google Cloud に認証

PowerShell で実行：

```powershell
gcloud auth login
```

- ブラウザが自動的に開きます
- Google アカウントでログインしてください
- 「Google Cloud CLI がアカウントへのアクセスをリクエストしています」 → **許可** をクリック

---

## ステップ 6: Google Cloud プロジェクト確認

PowerShell で実行：

```powershell
gcloud config list
```

出力例：
```
[core]
account = your-email@gmail.com
project = btc-trading-bot
```

**project の値が表示されたら OK です！**

もし `project = None` または表示されなかったら：

```powershell
gcloud projects list
```

プロジェクト一覧を確認して、プロジェクト ID をコピーしてください

```powershell
gcloud config set project YOUR_PROJECT_ID
```

---

## ステップ 7: デプロイ実行

PowerShell で以下を実行：

```powershell
cd C:\Users\user\Desktop\cursor\trade
python deploy.bat
```

または

```powershell
python start_cloud_deployment.py
```

---

## ✅ 完了！

デプロイが完了したら、以下で監視できます：

```powershell
python cloud_monitor.py --stats
```

---

## 🐛 トラブルシューティング

### エラー: "gcloud : 用語 'gcloud' は認識されません"

**解決**: 新しい PowerShell ウィンドウを開いてください（パスが更新されます）

### エラー: "Project not set"

**解決**:
```powershell
gcloud projects list
gcloud config set project YOUR_PROJECT_ID
```

### エラー: "Docker not installed"

**解決**: Docker Desktop をインストール
https://www.docker.com/products/docker-desktop

### エラー: "Permission denied"

**解決**: PowerShell を **管理者として実行** してください

---

## 📝 コピペ用コマンド集（順番に実行）

1. **Scoop インストール**:
```powershell
iwr -useb get.scoop.sh | iex
```

2. **Google Cloud SDK インストール**:
```powershell
scoop install gcloud
```
（PowerShell を閉じて、新しく開いてください）

3. **Google Cloud に認証**:
```powershell
gcloud auth login
```
（ブラウザで Google アカウントでログイン）

4. **プロジェクト設定確認**:
```powershell
gcloud config list
```

5. **デプロイ実行**:
```powershell
cd C:\Users\user\Desktop\cursor\trade
python deploy.bat
```

6. **デプロイ確認**:
```powershell
python cloud_monitor.py --stats
```

---

**ご不明な点があれば、各ステップを確実に実行してください。** 💪
