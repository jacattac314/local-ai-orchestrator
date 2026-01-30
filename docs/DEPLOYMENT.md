# Deployment Guide

## Overview

This guide covers deploying the Local AI Orchestrator in various environments, from development to production.

## Quick Start with Docker Compose

### Prerequisites
- Docker and Docker Compose installed
- - API keys for OpenRouter (required)
 
  - ### Steps
 
  - 1. **Clone the repository**
    2.    ```bash
             git clone https://github.com/jacattac314/local-ai-orchestrator.git
             cd local-ai-orchestrator
             ```

          2. **Create environment file**
          3.    ```bash
                   cp .env.example .env
                   ```

                3. **Configure your API keys**
                4.    ```bash
                         # Edit .env with your API keys
                         nano .env
                         ```

                         Minimum required:
                     ```env
                     OPENROUTER_API_KEY=your-key-here
                     ```al
      
                  | Variable | Default | Description |
            |----------|---------|-------------|
            | `DATABASE_URL` | `sqlite:///data/orchestrator.db` | Database connection string |
            | `ORCHESTRATOR_API_KEY` | None | API key for authentication (leave empty to disable) |
            | `ORCHESTRATOR_ALLOWED_DOMAINS` | Empty | Comma-separated URLs allowed for requests |
            | `ORCHESTRATOR_METRIC_RETENTION_DAYS` | 30 | Days to keep metrics data |
            | `ORCHESTRATOR_OFFLINE_MODE_ENABLED` | true | Enable offline cache fallback |
            | `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
      
            ### OpenRouter Sync
   
      | Variable | Default | Description |
    |----------|---------|-------------|
    | `OPENROUTER_SYNC_INTERVAL` | 3600 | Seconds between syncs (3600 = 1 hour) |
 
    ### LMSYS Arena Sync
 
    | Variable | Default | Description |
    |----------|---------|-------------|
    | `LMSYS_SYNC_INTERVAL` | 86400 | Seconds between syncs (86400 = 24 hours) |
 
    ### HuggingFace Sync
 
    | Variable | Default | Description |
    |----------|---------|-------------|
    | `HUGGINGFACE_SYNC_INTERVAL` | 86400 | Seconds between syncs |
 
    ### Scheduler
 
    | Variable | Default | Description |
    |----------|---------|-------------|
    | `SCHEDULER_TIMEZONE` | UTC | Timezone for scheduled tasks |
    | `SCHEDULER_MAX_WORKERS` | 4 | Max background worker threads |
 
    ### HTTP Client
 
    | Variable | Default | Description |
    |----------|---------|-------------|
    | `HTTP_TIMEOUT_CONNECT` | 10 | Connect timeout (seconds) |
    | `HTTP_TIMEOUT_READ` | 30 | Read timeout (seconds) |
    | `HTTP_MAX_RETRIES` | 3 | Max retry attempts |
 
    ## Deployment Options
 
    ### Option 1: Docker Compose (Development/Small Scale)
 
    **Best for**: Development, testing, single-server deployments
 
    **Pros**:
    - Simple setup
    - - Local development mirrors production
      - - Good for < 10k requests/day
       
        - **Cons**:
        - - Single point of failure
          - - Limited scalability
            - - SQLite database limitations
             
              - **Setup**:
              - ```bash
                docker-compose up -d
                ```
             
                ### Option 2: Docker on AWS/GCP/Azure
             
                **Best for**: Scalable cloud deployments
             
                #### AWS ECS Setup
             
                1. **Create RDS PostgreSQL instance**
                2.    ```bash
                         # Use AWS Console or CLI
                         aws rds create-db-instance \
                           --db-instance-identifier orchestrator-db \
                           --engine postgres \
                           --db-instance-class db.t3.micro
                         ```
             
                      2. **Build and push Docker image**
                      3.    ```bash
                               docker build -t orchestrator:latest .
                               docker tag orchestrator:latest YOUR_ECR_URI/orchestrator:latest
                               docker push YOUR_ECR_URI/orchestrator:latest
                               ```
             
                            3. **Create ECS cluster and task definition**
                            4.    - Use AWS Console to create cluster
                                  -    - Create task definition with the pushed image
                                       -    - Configure environment variables
                                            -    - Set DATABASE_URL to RDS connection string
                                             
                                                 - 4. **Deploy**
                                                   5.    - Create service in ECS cluster
                                                         -    - Configure auto-scaling
                                                              -    - Set up load balancer (ALB)
                                                               
                                                                   - #### Environment for Cloud
                                                               
                                                                   - ```env
                                                                     DATABASE_URL=postgresql://user:password@rds-endpoint:5432/orchestrator
                                                                     ORCHESTRATOR_API_KEY=generate-secure-key
                                                                     ORCHESTRATOR_ALLOWED_DOMAINS=yourdomain.com
                                                                     LOG_LEVEL=INFO
                                                                     ```
             
                                                                     ### Option 3: Kubernetes
             
                                                                     **Best for**: Enterprise, multi-region, high-volume deployments
             
                                                                     #### Prerequisites
                                                                     - Kubernetes cluster (EKS, GKE, AKS, etc.)
                                                                     - - `kubectl` configured
                                                                       - - PostgreSQL database
                                                                         - - Redis (optional, for distributed caching)
                                                                          
                                                                           - #### Steps
                                                                          
                                                                           - 1. **Create ConfigMap and Secrets**
                                                                             2.    ```bash
                                                                                      kubectl create secret generic orchestrator-secrets \
                                                                                        --from-literal=openrouter-api-key=YOUR_KEY \
                                                                                        --from-literal=orchestrator-api-key=YOUR_KEY

                                                                                      kubectl create configmap orchestrator-config \
                                                                                        --from-literal=database-url=postgresql://...
                                                                                      ```
             
                                                                                   2. **Apply Kubernetes manifests** (create `k8s/` directory)
                                                                                   3.    ```bash
                                                                                            kubectl apply -f k8s/namespace.yaml
                                                                                            kubectl apply -f k8s/deployment.yaml
                                                                                            kubectl apply -f k8s/service.yaml
                                                                                            kubectl apply -f k8s/ingress.yaml
                                                                                            kubectl apply -f k8s/hpa.yaml
                                                                                            ```
             
                                                                                         3. **Sample deployment.yaml**
                                                                                         4.    ```yaml
                                                                                                  apiVersion: apps/v1
                                                                                                  kind: Deployment
                                                                                                  metadata:
                                                                                                    name: orchestrator
                                                                                                    namespace: orchestrator
                                                                                                  spec:
                                                                                                    replicas: 3
                                                                                                    selector:
                                                                                                      matchLabels:
                                                                                                        app: orchestrator
                                                                                                    template:
                                                                                                      metadata:
                                                                                                        labels:
                                                                                                          app: orchestrator
                                                                                                      spec:
                                                                                                        containers:
                                                                                                        - name: orchestrator
                                                                                                          image: your-registry/orchestrator:latest
                                                                                                          ports:
                                                                                                          - containerPort: 8000
                                                                                                          env:
                                                                                                          - name: DATABASE_URL
                                                                                                            valueFrom:
                                                                                                              configMapKeyRef:
                                                                                                                name: orchestrator-config
                                                                                                                key: database-url
                                                                                                          - name: OPENROUTER_API_KEY
                                                                                                            valueFrom:
                                                                                                              secretKeyRef:
                                                                                                                name: orchestrator-secrets
                                                                                                                key: openrouter-api-key
                                                                                                          resources:
                                                                                                            requests:
                                                                                                              memory: "256Mi"
                                                                                                              cpu: "250m"
                                                                                                            limits:
                                                                                                              memory: "512Mi"
                                                                                                              cpu: "500m"
                                                                                                          livenessProbe:
                                                                                                            httpGet:
                                                                                                              path: /health
                                                                                                              port: 8000
                                                                                                            initialDelaySeconds: 30
                                                                                                            periodSeconds: 10
                                                                                                  ---
                                                                                                  apiVersion: v1
                                                                                                  kind: Service
                                                                                                  metadata:
                                                                                                    name: orchestrator
                                                                                                    namespace: orchestrator
                                                                                                  spec:
                                                                                                    type: ClusterIP
                                                                                                    ports:
                                                                                                    - port: 8000
                                                                                                      targetPort: 8000
                                                                                                    selector:
                                                                                                      app: orchestrator
                                                                                                  ---
                                                                                                  apiVersion: autoscaling/v2
                                                                                                  kind: HorizontalPodAutoscaler
                                                                                                  metadata:
                                                                                                    name: orchestrator
                                                                                                    namespace: orchestrator
                                                                                                  spec:
                                                                                                    scaleTargetRef:
                                                                                                      apiVersion: apps/v1
                                                                                                      kind: Deployment
                                                                                                      name: orchestrator
                                                                                                    minReplicas: 2
                                                                                                    maxReplicas: 10
                                                                                                    metrics:
                                                                                                    - type: Resource
                                                                                                      resource:
                                                                                                        name: cpu
                                                                                                        target:
                                                                                                          type: Utilization
                                                                                                          averageUtilization: 70
                                                                                                  ```
             
                                                                                               4. **Verify deployment**
                                                                                               5.    ```bash
                                                                                                        kubectl get pods -n orchestrator
                                                                                                        kubectl logs -n orchestrator deployment/orchestrator
                                                                                                        ```
             
                                                                                                     ## Database Setup
             
                                                                                                 ### SQLite (Development)
             
                                                                                           Default setup, no configuration needed:
                                                                                     ```env
                                                                                     DATABASE_URL=sqlite:///data/orchestrator.db
                                                                                     ```
             
                                                                                     ### PostgreSQL (Production)
             
                                                                               1. **Create database**
                                                                               2.    ```sql
                                                                                        CREATE DATABASE orchestrator;
                                                                                        CREATE USER orchestrator WITH PASSWORD 'secure-password';
                                                                                        GRANT ALL PRIVILEGES ON DATABASE orchestrator TO orchestrator;
                                                                                        ```
             
                                                                                     2. **Configure connection**
                                                                                     3.    ```env
                                                                                              DATABASE_URL=postgresql://orchestrator:secure-password@db-host:5432/orchestrator
                                                                                              ```
             
                                                                                           3. **Run migrations**
                                                                                           4.    ```bash
                                                                                                    # The application automatically creates tables on startup
                                                                                                    docker-compose up
                                                                                                    ```
             
                                                                                                 ### Backup & Recovery
             
                                                                                             **Regular backups** (PostgreSQL):
                                                                                       ```bash
                                                                                       pg_dump orchestrator > backup-$(date +%Y%m%d).sql
                                                                                       ```
             
                                                                                       **Restore**:
                                                                                 ```bash
                                                                                 psql orchestrator < backup-20240101.sql
                                                                                 ```
             
                                                                                 ## Monitoring & Health Checks
             
                                                                             ### Health Endpoint
             
                                                                             ```bash
                                                                             curl http://localhost:8000/health
                                                                             ```
             
                                                                             Response:
                                                                             ```json
                                                                             {
                                                                               "status": "healthy",
                                                                               "database": "connected",
                                                                               "cache": "ready"
                                                                             }
                                                                             ```
             
                                                                             ### Logging
             
                                                                             View logs:
                                                                             ```bash
                                                                             # Docker Compose
                                                                             docker-compose logs -f orchestrator

                                                                             # Kubernetes
                                                                             kubectl logs -f deployment/orchestrator -n orchestrator
                                                                             ```
             
                                                                             Configure log level:
                                                                             ```env
                                                                             LOG_LEVEL=DEBUG  # Verbose debugging
                                                                             LOG_LEVEL=INFO   # Standard logs
                                                                             LOG_LEVEL=WARNING # Only warnings and errors
                                                                             ```
             
                                                                             ### Metrics & Observability
             
                                                                             Access metrics endpoint:
                                                                             ```bash
                                                                             curl http://localhost:8000/metrics
                                                                             ```
             
                                                                             For advanced monitoring, integrate:
                                                                             - Prometheus for metrics collection
                                                                             - - Grafana for visualization
                                                                               - - Jaeger for distributed tracing
                                                                                
                                                                                 - ## Security Considerations
                                                                                
                                                                                 - ### API Key Management
                                                                                
                                                                                 - 1. **Enable API key authentication**
                                                                                   2.    ```env
                                                                                            ORCHESTRATOR_API_KEY=generate-secure-key
                                                                                            ```
             
                                                                                         2. **Use in requests**
                                                                                         3.    ```bash
                                                                                                  curl -H "Authorization: Bearer your-api-key" \
                                                                                                    http://localhost:8000/v1/chat/completions
                                                                                                  ```
             
                                                                                               3. **Rotate keys regularly**
                                                                                               4.    - Update in environment variables
                                                                                                     -    - Restart service
                                                                                                          -    - Update client applications
                                                                                                           
                                                                                                               - ### Network Security
                                                                                                           
                                                                                                               - 1. **HTTPS/TLS**: Use reverse proxy (nginx, Traefik)
                                                                                                                 2. 2. **SSRF Protection**: Configure `ORCHESTRATOR_ALLOWED_DOMAINS`
                                                                                                                    3. 3. **Rate Limiting**: Implement with reverse proxy
                                                                                                                       4. 4. **Firewall**: Restrict database access to application only
                                                                                                                         
                                                                                                                          5. ### Database Security
                                                                                                                         
                                                                                                                          6. 1. Use PostgreSQL in production (not SQLite)
                                                                                                                             2. 2. Enable SSL connections to database
                                                                                                                                3. 3. Use strong, random passwords
                                                                                                                                   4. 4. Run with minimal privileges
                                                                                                                                     
                                                                                                                                      5. ## Scaling Recommendations
                                                                                                                                     
                                                                                                                                      6. | Load | Deployment | Database | Caching |
                                                                                                                                      7. |------|-----------|----------|---------|
                                                                                                                                      8. | < 10k req/day | Docker Compose | SQLite | Local |
                                                                                                                                      9. | 10k-100k req/day | Single Docker | PostgreSQL | Redis |
                                                                                                                                      10. | > 100k req/day | Kubernetes | PostgreSQL | Redis Cluster |
                                                                                                                                     
                                                                                                                                      11. ## Troubleshooting
                                                                                                                                     
                                                                                                                                      12. ### Service won't start
                                                                                                                                     
                                                                                                                                      13. Check logs:
                                                                                                                                      14. ```bash
                                                                                                                                          docker-compose logs orchestrator
                                                                                                                                          ```
             
                                                                                                                                          Common issues:
                                                                                                                                          - Missing API keys - Add to `.env`
                                                                                                                                          - - Port already in use - Change `ports` in docker-compose.yml
                                                                                                                                            - - Database connection - Verify `DATABASE_URL`
                                                                                                                                             
                                                                                                                                              - ### Slow responses
                                                                                                                                             
                                                                                                                                              - Optimize:
                                                                                                                                              - 1. Increase cache TTL
                                                                                                                                                2. 2. Reduce sync intervals
                                                                                                                                                   3. 3. Add database indexes
                                                                                                                                                      4. 4. Scale to multiple instances
                                                                                                                                                        
                                                                                                                                                         5. ### Database connection errors
                                                                                                                                                        
                                                                                                                                                         6. ```bash
                                                                                                                                                            # Test connection
                                                                                                                                                            docker-compose exec db psql -U orchestrator -d orchestrator

                                                                                                                                                            # Check connection string
                                                                                                                                                            echo $DATABASE_URL
                                                                                                                                                            ```
             
                                                                                                                                                            ## Maintenance
             
                                                                                                                                                            ### Regular Tasks
             
                                                                                                                                                            - **Weekly**: Check logs for errors
                                                                                                                                                            - - **Monthly**: Review metrics and performance
                                                                                                                                                              - - **Quarterly**: Update dependencies
                                                                                                                                                                - - **Annually**: Security audit
                                                                                                                                                                 
                                                                                                                                                                  - ### Updates
                                                                                                                                                                 
                                                                                                                                                                  - 1. Pull latest code
                                                                                                                                                                    2.    ```bash
                                                                                                                                                                             git pull origin master
                                                                                                                                                                             ```
             
                                                                                                                                                                          2. Test changes
                                                                                                                                                                          3.    ```bash
                                                                                                                                                                                   make test
                                                                                                                                                                                   ```
             
                                                                                                                                                                                3. Rebuild Docker image
                                                                                                                                                                                4.    ```bash
                                                                                                                                                                                         docker-compose build
                                                                                                                                                                                         ```
             
                                                                                                                                                                                      4. Deploy with zero downtime
                                                                                                                                                                                      5.    ```bash
                                                                                                                                                                                               docker-compose up -d  # Graceful restart
                                                                                                                                                                                               ```
             
                                                                                                                                                                                            ## Support
             
                                                                                                                                                                                        For deployment issues:
                                                                                                                                                                                  - Check logs and error messages
                                                                                                                                                                                  - - Review [ARCHITECTURE.md](ARCHITECTURE.md) for system design
                                                                                                                                                                                    - - See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup
                                                                                                                                                                                      - - Open GitHub issue with detailed logs and configuration

                  4. **Start the services**
                  5.    ```bash
                           docker-compose up -d
                           ```

                        5. **Verify deployment**
                        6.    ```bash
                                 curl http://localhost:8000/health
                                 ```

                              6. **Access the API**
                              7.    - REST API: `http://localhost:8000`
                                    -    - API Docs: `http://localhost:8000/docs`
                                         -    - ReDoc: `http://localhost:8000/redoc`
                                          
                                              - ### Stopping Services
                                          
                                              - ```bash
                                                docker-compose d
