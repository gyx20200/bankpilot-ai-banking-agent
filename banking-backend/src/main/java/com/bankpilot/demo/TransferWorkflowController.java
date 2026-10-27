package com.bankpilot.demo;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/transfers")
public class TransferWorkflowController {
    private final TransferWorkflowService workflow;
    private final DemoOtpVault otpVault;
    private final boolean debugOtpEnabled;

    public TransferWorkflowController(TransferWorkflowService workflow, DemoOtpVault otpVault,
          @Value("${bankpilot.demo.otp.debug-enabled:false}") boolean debugOtpEnabled) {
        this.workflow=workflow; this.otpVault=otpVault; this.debugOtpEnabled=debugOtpEnabled;
    }

    public record AuthorizationRequest(Boolean confirmed, String otp) { }

    @GetMapping("/{orderId}")
    public TransferWorkflowService.StatusView status(@PathVariable long orderId) {
        return workflow.status(AuthenticatedUser.id(),orderId);
    }

    @PostMapping("/{orderId}/otp/request")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public TransferWorkflowService.OtpView requestOtp(@PathVariable long orderId) {
        return workflow.requestOtp(AuthenticatedUser.id(),orderId);
    }

    @PostMapping("/{orderId}/authorize")
    public TransferWorkflowService.ApprovalView authorize(@PathVariable long orderId,
            @RequestBody AuthorizationRequest request) {
        if (request == null || request.confirmed() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"confirmed is required");
        }
        return workflow.authorize(AuthenticatedUser.id(),orderId,request.confirmed(),request.otp());
    }

    @PostMapping("/{orderId}/execute")
    public TransferWorkflowService.StatusView execute(@PathVariable long orderId) {
        return workflow.execute(AuthenticatedUser.id(),orderId);
    }


    @PostMapping("/{orderId}/cancel")
    public TransferWorkflowService.StatusView cancel(@PathVariable long orderId) {
        return workflow.cancel(AuthenticatedUser.id(), orderId);
    }

    /** Exposes FAKE OTP to the SAME local browser solely for contest demonstration.
     * Always disabled unless explicitly enabled AND called from loopback.
     */
    @GetMapping("/{orderId}/demo-otp")
    public Map<String,String> demoOtp(@PathVariable long orderId, HttpServletRequest request) {
        if (!debugOtpEnabled || !("127.0.0.1".equals(request.getRemoteAddr()) ||
                "0:0:0:0:0:0:0:1".equals(request.getRemoteAddr()) || "::1".equals(request.getRemoteAddr()))) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo OTP endpoint disabled");
        }
        long userId=AuthenticatedUser.id();
        workflow.status(userId,orderId); // authz check before disclosing local test code
        return Map.of("otp",otpVault.getDebugCode(orderId,userId),"warning","LOCAL_DEMO_ONLY_NOT_REAL_MFA");
    }
}
