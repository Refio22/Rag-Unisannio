# Use the official Solr image from Docker Hub
FROM solr:latest

# Expose the Solr port
EXPOSE 8983

# Start Solr in the background
RUN solr start && \
    sleep 10 && \
    solr create_core -c regolamento_1

# Start Solr in the foreground
CMD ["solr-foreground"]
