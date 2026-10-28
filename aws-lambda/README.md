# AWS Lambda Functions

This directory contains the Python 3.14 scripts that were deployed to AWS Lambda via the online console.

## Lambda Configuration
### General Configuration
**Runtime:** Python 3.14     
**Architecture:** arm64       
**Memory:** 128 MB      
**Storage:** 512 MB       
**Timeout:** 1 minute    
**VPC:** None (requires an expensive NAT Gateway)

### Logs
**Log Format** JSON   
**Application Log Level:** WARN    
**System Log Level:** WARN    
**Log Group:** Default    

### Asynchronous Invocation and Concurrency
**Retry Attempts:** 0      
**Reserve Concurrency:** 1     
