package ai.builderr.signalpost.security;

import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicInteger;

@Component
public class GuardRailController {

    private static final int PLANNED_HTTP_REQUEST_MAX_CAP = 2000;
    private final AtomicInteger aggregatedNetworkRequests = new AtomicInteger(0);

    public void incrementNetworkCalls(int countsToIncrement) {
        int currentTotalCalls = aggregatedNetworkRequests.addAndGet(countsToIncrement);
        if (currentTotalCalls >= (PLANNED_HTTP_REQUEST_MAX_CAP - 50)) {
            throw new SecurityException("CRITICAL HTTP CAP BREACH PREVENTED: Hitting evaluation boundaries.");
        }
    }

    public int getCurrentCalls() {
        return aggregatedNetworkRequests.get();
    }

    public int getMaxCap() {
        return PLANNED_HTTP_REQUEST_MAX_CAP;
    }
}
