#include "measurement_pipeline.h"

#include <cmath>
#include <ctime>
#include <cstdio>
#include <sstream>
#include <vector>

namespace {

double measure_channel_once(int channel, Plant plant) {
    return plant_measure(channel, plant);
}

bool measure_stable_channel(
    int channel,
    Plant plant,
    const MeasurementOptions& options,
    double* value,
    std::string* error_message
) {
    if (options.stability_reads <= 1) {
        *value = measure_channel_once(channel, plant);
        return true;
    }

    const double reference = measure_channel_once(channel, plant);
    double current = reference;

    for (int i = 1; i < options.stability_reads; ++i) {
        current = measure_channel_once(channel, plant);
        if (std::fabs(current - reference) > options.stability_tolerance) {
            std::ostringstream stream;
            stream
                << "Channel " << channel
                << " is unstable: reference=" << reference
                << ", current=" << current
                << ", tolerance=" << options.stability_tolerance;
            *error_message = stream.str();
            return false;
        }
    }

    *value = current;
    return true;
}

double calculate_average(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }

    double sum = 0.0;
    for (size_t i = 0; i < values.size(); ++i) {
        sum += values[i];
    }
    return sum / static_cast<double>(values.size());
}

double calculate_variance(const std::vector<double>& values, double average) {
    if (values.empty()) {
        return 0.0;
    }

    double sum = 0.0;
    for (size_t i = 0; i < values.size(); ++i) {
        const double delta = values[i] - average;
        sum += delta * delta;
    }
    return sum / static_cast<double>(values.size());
}

}  // namespace

MeasurementResult run_measurements(
    int frame_count,
    Plant plant,
    const MeasurementOptions& options
) {
    MeasurementResult result;
    result.success = false;

    if (frame_count <= 0) {
        result.error_message = "Frame count must be positive";
        return result;
    }

    if (options.channel6_reads <= 0) {
        result.error_message = "Channel 6 read count must be positive";
        return result;
    }

    result.frames.reserve(static_cast<size_t>(frame_count));

    for (int frame_index = 1; frame_index <= frame_count; ++frame_index) {
        MeasurementFrame frame;
        frame.number = 0;
        frame.channel_1 = 0.0;
        frame.channel_2 = 0.0;
        frame.channel_3 = 0.0;
        frame.channel_4 = 0.0;
        frame.channel_5 = 0;
        frame.channel_6_avg = 0.0;
        frame.channel_6_disp = 0.0;
        frame.channel_19 = 0.0;
        frame.channel_49 = 0.0;
        frame.channel_69_func = 0.0;
        frame.number = frame_index;

        double channel_value = 0.0;
        if (!measure_stable_channel(1, plant, options, &channel_value, &result.error_message)) {
            return result;
        }
        frame.channel_1 = channel_value;

        if (!measure_stable_channel(2, plant, options, &channel_value, &result.error_message)) {
            return result;
        }
        frame.channel_2 = channel_value;

        if (!measure_stable_channel(3, plant, options, &channel_value, &result.error_message)) {
            return result;
        }
        frame.channel_3 = channel_value;

        if (!measure_stable_channel(4, plant, options, &channel_value, &result.error_message)) {
            return result;
        }
        frame.channel_4 = channel_value;

        if (!measure_stable_channel(5, plant, options, &channel_value, &result.error_message)) {
            return result;
        }
        frame.channel_5 = static_cast<int>(channel_value);

        std::vector<double> channel6_values;
        channel6_values.reserve(static_cast<size_t>(options.channel6_reads));
        for (int i = 0; i < options.channel6_reads; ++i) {
            channel6_values.push_back(measure_channel_once(6, plant));
        }

        frame.channel_6_avg = calculate_average(channel6_values);
        frame.channel_6_disp = calculate_variance(channel6_values, frame.channel_6_avg);
        frame.channel_19 = measure_channel_once(19, plant);
        frame.channel_49 = measure_channel_once(49, plant);
        frame.channel_69_func = measure_channel_once(69, plant);

        result.frames.push_back(frame);
    }

    result.success = true;
    result.end_time_msk = format_current_msk_time();
    return result;
}

std::string format_current_msk_time() {
    const std::time_t raw_time = std::time(NULL) + (3 * 60 * 60);
    const std::tm* utc_time = std::gmtime(&raw_time);

    if (utc_time == NULL) {
        return "";
    }

    char buffer[20] = {0};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", utc_time);
    return std::string(buffer);
}
