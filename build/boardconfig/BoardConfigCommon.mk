include vendor/extras/build/boardconfig/BoardConfigKernel.mk

ifeq ($(BOARD_USES_QCOM_HARDWARE),true)
include vendor/extras/build/boardconfig/BoardConfigQcom.mk
endif

include vendor/extras/build/boardconfig/BoardConfigSoong.mk
