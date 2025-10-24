后端运行是正常的@https://kingresearch-production.up.railway.app/ 
打开输出{"name":"DeerFlow API","version":"0.1.0","status":"running","docs":"/api/docs"}
variable是LANGGRAPH_CHECKPOINT_SAVER="true"
LANGGRAPH_CHECKPOINT_DB_URL="${{Postgres.DATABASE_URL}}"
JWT_SECRET_KEY="-XTTNxwPhkWvBbmpqA8NiZkJCx2U6pNg4I24YH_N31o"
ALLOWED_ORIGINS="https://kingresearch.up.railway.app"
SEARCH_API="tavily"
TAVILY_API_KEY="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"
ENVIRONMENT="production"
LOG_LEVEL="info"
前端运行也正常@https://kingresearch.up.railway.app/chat 
variable是NEXT_TELEMETRY_DISABLED="1"
SKIP_ENV_VALIDATION="1"
NEXT_PUBLIC_API_URL="https://kingresearch-production.up.railway.app/api/"
NODE_ENV="production"
但是进入前端页面中发现根本没有连接上后端