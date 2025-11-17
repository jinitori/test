from flask import Flask, request
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2 import service_account
import base64
import os

app = Flask(__name__)

# ---------------------------
# Gmail API 보내기
# ---------------------------
def send_email(to_email, subject, body):

    # 🔥 Cloud Run에 Secret Manager로부터 마운트될 경로
    service_key_path = os.environ.get("SERVICE_KEY_PATH", "/secrets/secret")

    creds = service_account.Credentials.from_service_account_file(
        service_key_path,
        scopes=["https://www.googleapis.com/auth/gmail.send"]
    )
    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(body, _charset="UTF-8")
    message["to"] = to_email
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()


# ---------------------------
# 오늘 기사 크롤링
# ---------------------------
def get_today_competitor_news_html_filtered(
    competitors: list,
    similarity_threshold: float = 0.8
) -> pd.DataFrame:

    headers = {"User-Agent": "Mozilla/5.0"}
    all_articles = []
    today = datetime.now().date()

    for comp in competitors:
        url = f"https://www.google.com/search?q={quote(comp)}&tbm=nws&hl=ko"
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")

        news_blocks = soup.select("div.dbsr")

        for item in news_blocks:
            try:
                title = item.select_one("div[role='heading']").text.strip()
                link = item.a["href"]
                snippet_tag = item.select_one(".Y3v8qd")
                snippet = snippet_tag.text.strip() if snippet_tag else ""

                time_tag = item.select_one("time")
                published_str = time_tag.get("datetime") if time_tag else ""
                published = None
                if published_str:
                    try:
                        published = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        )
                    except:
                        published = None

                if not published or published.date() != today:
                    continue

                all_articles.append({
                    "경쟁사": comp,
                    "제목": title,
                    "요약": snippet,
                    "링크": link,
                    "게시일": published.strftime("%Y-%m-%d %H:%M")
                })

            except Exception:
                continue

    df = pd.DataFrame(all_articles)
    if df.empty:
        return df

    df.drop_duplicates(subset=["링크"], inplace=True)

    texts = df["제목"] + " " + df["요약"]
    vectorizer = TfidfVectorizer(max_features=3000)
    tfidf_matrix = vectorizer.fit_transform(texts)
    cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)

    to_drop = set()
    for i in range(len(df)):
        if i in to_drop:
            continue
        dup_idx = np.where(cosine_sim[i] > similarity_threshold)[0]
        dup_idx = [idx for idx in dup_idx if idx != i]
        to_drop.update(dup_idx)

    df_filtered = df.drop(index=to_drop).reset_index(drop=True)
    return df_filtered


# ---------------------------
# Cloud Run 엔드포인트
# ---------------------------
@app.route("/", methods=["POST", "GET"])
def run():
    competitors = [
        "쿠팡", "네이버", "오아시스", "SSG",
        "올리브영", "오늘의집", "무신사", "배달의민족"
    ]

    EMAIL_LIST = [
        "hyeonglae.cho@kurlycorp.com",
        "soaringfay@gmail.com"
    ]

    df = get_today_competitor_news_html_filtered(
        competitors,
        similarity_threshold=0.1
    )

    if df.empty:
        body = "📭 오늘 날짜의 경쟁사 뉴스가 없습니다."
    else:
        lines = []
        for _, row in df.iterrows():
            lines.append(f"[{row['경쟁사']}] {row['제목']}\n{row['링크']}\n")
        body = "\n".join(lines)

    for email in EMAIL_LIST:
        send_email(
            to_email=email,
            subject=f"[경쟁사 오늘 뉴스] {datetime.now().strftime('%Y-%m-%d')}",
            body=body
        )

    return "OK", 200


# ---------------------------
# Cloud Run Flask 실행
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
