# Use the official Solr image from Docker Hub
FROM solr:latest

# Expose the Solr port
EXPOSE 8983

# Copy your Solr configuration files if needed
# COPY ./solr_config /opt/solr/server/solr/configsets

# Set up the Solr core
RUN solr create_core -c regolamento_1

# Start Solr in the foreground
CMD ["solr-foreground"]
