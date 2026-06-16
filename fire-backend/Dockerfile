FROM maven:3.9.5-eclipse-temurin-21 AS builder
ARG APP_VERSION=dev
WORKDIR /app

# Keep base packages minimal
RUN apt-get update \
	&& apt-get install -y --no-install-recommends dos2unix ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

COPY pom.xml ./
# download dependencies ahead of copying sources for caching
RUN mvn -B -DskipTests dependency:go-offline

COPY . /app
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre-jammy
ARG APP_VERSION=dev
LABEL org.opencontainers.image.version="${APP_VERSION}"
WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl \
	&& rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 appuser || true \
	&& useradd -u 1000 -g appuser -m -s /usr/sbin/nologin appuser || true

COPY --from=builder /app/target/*.jar app.jar
RUN chown appuser:appuser /app/app.jar

RUN mkdir -p /var/log/fire-backend && chown -R appuser:appuser /var/log/fire-backend

USER appuser
EXPOSE 8181

COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
