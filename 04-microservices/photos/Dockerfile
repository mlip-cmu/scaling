# The photo service (Java, only the JDK). compose.yaml gives the data as the build context "data".
# Stage 1: compile with the JDK. Stage 2: run with the smaller JRE.
FROM eclipse-temurin:25-jdk-alpine AS build
WORKDIR /src
COPY PhotosService.java ./
RUN javac -d classes PhotosService.java

FROM eclipse-temurin:25-jre-alpine
WORKDIR /app
COPY --from=data photos.csv ./
COPY --from=build /src/classes ./classes
EXPOSE 8000
CMD ["java", "-cp", "classes", "PhotosService"]
