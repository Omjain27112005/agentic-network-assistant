# 🧠 Agentic Network Assistant
### *An AI-powered, real-time network monitoring platform — inspired by Juniper Marvis AI*

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Kafka](https://img.shields.io/badge/Apache_Kafka-7.5-orange?logo=apachekafka)](https://kafka.apache.org)
[![Redis](https://img.shields.io/badge/Redis-7.2-red?logo=redis)](https://redis.io)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)

---

## 🎯 What Is This?

A production-level **AI-powered network monitoring system** that:

- **Monitors** 10 virtual network devices (routers, switches, access points) in real-time
- **Detects** anomalies using threshold-based alert engine
- **Diagnoses** root cause autonomously using an AI Agent (Groq LLM + ReAct pattern)
- **Auto-creates** Jira tickets for critical incidents
- **Streams** live data to a React dashboard via WebSocket
- **Answers** engineer questions in plain English via AI chat interface

### Real-World Inspiration
> This project is a mini version of **Juniper Mist AI + Marvis** — Juniper Networks' flagship AI-driven network operations product, now part of HPE.

---

## 🏗️ Architecture

```
Network Simulator → Kafka → Metrics Processor → Redis → FastAPI → React Dashboard
                         → Alert Engine → Kafka → AI Agent → Action Executor → Jira + PostgreSQL
```

### Microservices

| Service | Responsibility |
|---|---|
| `network_simulator` | Generates realistic metrics for 10 virtual devices every 5s |
| `metrics_processor` | Consumes Kafka → stores in Redis with TTL |
| `alert_engine` | Threshold-based anomaly detection → publishes alerts |
| `ai_agent` | ReAct loop: Observe → Think → Act using Groq LLM |
| `action_executor` | Creates Jira tickets, stores incidents in PostgreSQL |
| `api_gateway` | FastAPI REST + WebSocket server |
| `frontend` | React dashboard with live charts and AI chat |

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3.11, FastAPI | Services + REST API |
| **Streaming** | Apache Kafka | Event bus between services |
| **Cache** | Redis | Live metrics, alerts, chat memory |
| **Database** | PostgreSQL | Incident history (permanent) |
| **AI** | Groq (LLaMA 3 70B) | Agentic reasoning + chat |
| **Frontend** | React + Vite | Real-time dashboard |
| **Charts** | Recharts | Metric visualization |
| **State** | Zustand | React global state |
| **Infra** | Docker Compose | Local development stack |

---

## 🚀 Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 18+
- Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/agentic-network-assistant.git
cd agentic-network-assistant
```

### 2. Setup environment
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY and JIRA credentials
```

### 3. Start infrastructure
```bash
docker-compose up -d
# Kafka UI:     http://localhost:8080
# Redis UI:     http://localhost:8081
```

### 4. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 5. Start backend services (each in separate terminal)
```bash
python -m services.network_simulator.main
python -m services.metrics_processor.main
python -m services.alert_engine.main
python -m services.ai_agent.main
python -m services.action_executor.main
python -m services.api_gateway.main
```

### 6. Start React frontend
```bash
cd frontend
npm install
npm run dev
# Dashboard: http://localhost:5173
```

---

## 📁 Project Structure

```
agentic-network-assistant/
├── services/              # 6 independent microservices
│   ├── network_simulator/ # Service 1 — device metric generator
│   ├── metrics_processor/ # Service 2 — Kafka → Redis
│   ├── alert_engine/      # Service 3 — anomaly detection
│   ├── ai_agent/          # Service 4 — Groq LLM ReAct loop
│   ├── action_executor/   # Service 5 — Jira + PostgreSQL
│   └── api_gateway/       # Service 6 — FastAPI REST + WebSocket
├── frontend/              # React + Vite dashboard
├── shared/                # Shared models, Kafka, Redis utils
├── database/              # PostgreSQL schema
├── docker-compose.yml     # Infrastructure stack
├── requirements.txt
└── .env.example
```

---

## 🧪 How It Works — End to End

1. **Network Simulator** publishes device metrics to Kafka every 5 seconds
2. **Metrics Processor** stores them in Redis (TTL = 60s)
3. **Alert Engine** checks thresholds → if breached, publishes alert to Kafka
4. **AI Agent** consumes alert → runs ReAct loop:
   - *Observe*: fetches all related device metrics from Redis
   - *Think*: sends context to Groq LLM → gets root cause analysis
   - *Act*: publishes action (create ticket, log incident)
5. **Action Executor** creates Jira ticket + stores incident in PostgreSQL
6. **API Gateway** serves live data to React via WebSocket + REST
7. **React Dashboard** shows real-time device health, alerts, incidents
8. **AI Chat** lets engineers ask questions: *"What's wrong with R1?"*

---

## 🎓 Built For

This project demonstrates:
- **Distributed systems** (Kafka, microservices)
- **Real-time systems** (WebSocket, Redis)
- **Agentic AI** (ReAct pattern, LLM tool calling)
- **Production practices** (typed models, structured logging, Docker)
- **Enterprise integrations** (Jira API)

---

## 📝 License

MIT License — feel free to use for learning and interviews!
