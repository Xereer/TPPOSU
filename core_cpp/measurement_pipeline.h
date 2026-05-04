#ifndef MEASUREMENT_PIPELINE_H
#define MEASUREMENT_PIPELINE_H

#include <string>
#include <vector>

#include "plant.h"

struct MeasurementFrame {
    int number;
    double channel_1;
    double channel_2;
    double channel_3;
    double channel_4;
    int channel_5;
    double channel_6_avg;
    double channel_6_disp;
    double channel_19;
    double channel_49;
    double channel_69_func;
};

struct MeasurementOptions {
    int stability_reads;
    double stability_tolerance;
    int channel6_reads;

    MeasurementOptions()
        : stability_reads(1),
          stability_tolerance(0.0),
          channel6_reads(10) {
    }
};

struct MeasurementResult {
    bool success;
    std::string error_message;
    std::vector<MeasurementFrame> frames;
    std::string end_time_msk;
};

MeasurementResult run_measurements(
    int frame_count,
    Plant plant,
    const MeasurementOptions& options
);

std::string format_current_msk_time();

#endif
