# DBA Deal-Finding System: Final Implementation Plan with Self-Hosted Model Option

## Executive Summary  
Develop a modular scraper–filter–AI pipeline with a lean, interactive web UI using Python and HTMX. Begin with an LLM-first MVP (GPT/Claude) for rapid validation, then transition to a self-hosted multimodal model using standard interfaces (e.g., Hugging Face Inference API, LangChain) to reduce costs and increase control.

***

## System Architecture Overview

### 1. Web Scraper Module  
- **Framework:** Scrapy (with Selenium fallback)  
- **Features:** Pagination, rate limiting, proxy rotation, retry logic  
- **Data Extracted:** Title, price, description, images, location, timestamp  

### 2. Static Filter Engine  
- **Rules:** Price thresholds, include/exclude keywords, age/location filters  
- **Implementation:** Configurable Python class for boolean logic  

### 3. LLM Integration Layer (MVP)  
- **Purpose:** Offload classification/relevance to cloud LLMs  
- **Workflow:** Batch prompts, parse JSON responses  
- **Transition Data:** Collect LLM-labeled examples for model training  

### 4. Self-Hosted Model Layer (Phase 2)  
- **Model Options:**  
  - **Multimodal:** Fine-tuned CLIP or OpenCLIP variants  
  - **Text-Only LLM:** LLaMA / Vicuna / Mistral hosted via Hugging Face Inference or local Triton server  
- **Interface:**  
  - Use **LangChain** or **FastAPI endpoints** with consistent JSON schema  
  - Standardize calls (`/classify`) accepting `{"text":…, "image":…}`  
- **Advantages:**  
  - Lower long-term costs vs. API calls  
  - Data privacy and compliance  
  - Custom fine-tuning on collected examples  

### 5. Data Pipeline & Storage  
- **Database:** PostgreSQL + pgvector for embeddings  
- **Cache & Queue:** Redis for image cache, job scheduling, and model inferences  
- **Ranking:** Composite “deal score” integrating static rules, LLM confidence, self-hosted model scores  

***

## User Interaction & Web Interface Strategy

### Why a Web Interface?  
- Universal browser access  
- Live updates via SSE/WebSockets  
- Centralized query and notification management  

### Backend Framework: FastAPI + HTMX  
- **FastAPI:** Async APIs, WebSockets, OpenAPI  
- **HTMX:** Declarative AJAX/SSE for dynamic UI fragments  
- **Templating & Styling:** Jinja2 + Tailwind CSS  

### Minimal UI Deliverables  
1. **Search Dashboard**  
   - Live query form (`hx-get`, delay:500ms)  
   - Filters sidebar with static and AI-based toggles  
   - Paginated product grid with thumbnails, price, “deal score”  

2. **Listing Detail Panel**  
   - Image carousel, full description  
   - Classification verdict from LLM/self-hosted model  
   - “Favorite” and “Notify me” actions  

3. **Real-Time Alerts**  
   - SSE channel (`hx-sse`) for new matches  
   - Toast notifications linking to detail view  

4. **User Preferences**  
   - Saved queries and model selection (cloud LLM vs. self-hosted)  
   - Price and confidence thresholds  
   - Notification settings (email/SSE)  

***

## Technical Implementation Phases

### Phase 1 (Weeks 1–2): MVP with Cloud LLM  
- Scrapy spider, static filters, FastAPI skeleton  
- LLM integration layer with prompt templates  
- Search dashboard UI with HTMX live results  

### Phase 2 (Weeks 3–4): Self-Hosted Model Integration  
- Deploy CLIP and/or LLaMA-based models via Hugging Face Inference or local Triton  
- Build standardized `/classify` endpoint in FastAPI  
- UI toggle to switch between LLM API and self-hosted model  

### Phase 3 (Weeks 5–6): Fine-Tuning & Optimization  
- Fine-tune self-hosted models on collected LLM-labeled data  
- Benchmark classification accuracy and inference latency  
- Implement batching, caching, and image downscaling  

### Phase 4 (Weeks 7–8): Production Hardening  
- Docker/Kubernetes deployment for scraping workers and model servers  
- Monitoring (Prometheus/Grafana), logging, and alerting  
- Comprehensive documentation and handover  

***

## Deployment & Cost Optimization  
- **Containers:** Docker Compose; Kubernetes for scale  
- **Model Hosting:** Self-hosted on GPU server or managed inference  
- **Batching & Caching:** Aggregate classification requests; cache embeddings  
- **Image Processing:** Downscale to 224×224 for CLIP; JPEG compression  

***

## Deliverables

1. **Core Modules**  
   - Scrapy-based scraper with dynamic content support  
   - Static filtering engine  
   - LLM integration layer (cloud APIs)  
   - Self-hosted model layer with standard JSON interface  

2. **UI Components**  
   - HTMX-powered search dashboard and detail panel  
   - Real-time SSE/WebSocket alerts  
   - User preferences for model selection  

3. **Infrastructure & Tooling**  
   - Docker/Kubernetes manifests for scraper, API, and model servers  
   - CI/CD pipeline with automated model deployments  
   - Monitoring and alerting setup  

4. **Documentation**  
   - Technical architecture and API reference  
   - LLM prompting guide and self-hosted model interfacing  
   - UI/UX patterns with HTMX  
   - Deployment and scaling handbook  
