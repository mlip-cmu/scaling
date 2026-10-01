// The photo service (Java): the metadata of the photos. It uses only the JDK: its HTTP server
// and no JSON library (the service only writes JSON).
//
// Its data: its own copy of the photos table (photos.csv).

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

public class PhotosService {

    record Photo(long photoId, long userId, String path, String uploaded, String title) {
        String toJson() {
            return "{\"photo_id\":%d,\"user_id\":%d,\"path\":%s,\"uploaded\":%s,\"title\":%s}"
                    .formatted(photoId, userId, json(path), json(uploaded), json(title));
        }
    }

    static final Map<Long, Photo> photos = new HashMap<>();

    public static void main(String[] args) throws IOException {
        List<String> lines = Files.readAllLines(Path.of("photos.csv"));
        List<String> header = parseCsvLine(lines.get(0));
        for (String line : lines.subList(1, lines.size())) {
            List<String> values = parseCsvLine(line);
            Map<String, String> row = new HashMap<>();
            for (int i = 0; i < header.size(); i++) row.put(header.get(i), values.get(i));
            Photo p = new Photo(
                    Long.parseLong(row.get("photo_id")),
                    Long.parseLong(row.get("user_id")),
                    row.get("path"),
                    row.get("upload_date"),
                    row.get("title").isEmpty() ? null : row.get("title"));
            photos.put(p.photoId(), p);
        }

        HttpServer server = HttpServer.create(new InetSocketAddress(8000), 0);
        server.createContext("/photos", PhotosService::handle);
        server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
        server.start();
        System.out.println("photos: " + photos.size() + " photos, port 8000");
    }

    static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            String path = exchange.getRequestURI().getPath();
            String query = exchange.getRequestURI().getRawQuery();
            if (path.equals("/photos")) { // several photos in one call: /photos?ids=1,2,3
                String ids = queryParameter(query, "ids");
                if (ids == null) {
                    send(exchange, 422, "{\"detail\":\"the parameter ids is missing\"}");
                    return;
                }
                List<String> found = new ArrayList<>();
                for (String id : ids.split(",")) {
                    Photo p = photos.get(parseId(id));
                    if (p != null) found.add(p.toJson());
                }
                send(exchange, 200, "[" + String.join(",", found) + "]");
            } else { // one photo: /photos/133422131
                Photo p = photos.get(parseId(path.substring("/photos/".length())));
                if (p == null) send(exchange, 404, "{\"detail\":\"no such photo\"}");
                else send(exchange, 200, p.toJson());
            }
        }
    }

    static void send(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    static long parseId(String s) {
        try {
            return Long.parseLong(s.strip());
        } catch (NumberFormatException e) {
            return -1; // no photo has this ID
        }
    }

    static String queryParameter(String query, String name) {
        if (query == null) return null;
        Map<String, String> params = Arrays.stream(query.split("&"))
                .map(kv -> kv.split("=", 2))
                .collect(Collectors.toMap(
                        kv -> kv[0],
                        kv -> kv.length > 1 ? URLDecoder.decode(kv[1], StandardCharsets.UTF_8) : "",
                        (a, b) -> b));
        return params.get(name);
    }

    // One line of a CSV file; a value in double quotes can contain commas ("ƒ/2, 1/15").
    static List<String> parseCsvLine(String line) {
        List<String> values = new ArrayList<>();
        StringBuilder value = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (quoted && c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                value.append('"'); // "" in quotes is one "
                i++;
            } else if (c == '"') {
                quoted = !quoted;
            } else if (c == ',' && !quoted) {
                values.add(value.toString());
                value.setLength(0);
            } else {
                value.append(c);
            }
        }
        values.add(value.toString());
        return values;
    }

    static String json(String s) {
        if (s == null) return "null";
        StringBuilder out = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                default -> {
                    if (c < 0x20) out.append("\\u%04x".formatted((int) c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }
}
