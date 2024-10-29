# Use the official Solr image from Docker Hub
FROM solr:latest

# Expose the Solr port
EXPOSE 8983

# Create the Solr home directory structure
RUN mkdir -p /var/solr/data

# Start Solr in the background, wait for it to initialize, and create the core
RUN solr start -Dsolr.solr.home=/var/solr/data && \
    sleep 10 && \
    solr create_core -c regolamento_1

# Start Solr in the foreground
CMD ["solr-foreground"]
