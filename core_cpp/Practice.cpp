#include "measurement_pipeline.h"
#include "plant.h"

#include <iostream>
#include <sstream>

using namespace std;

int
main(int argc, char* argv[]) {
    if (argc < 2) {
        cerr << "Usage: Practice <frame_count> [stability_reads] [stability_tolerance] [channel6_reads]" << '\n';
        return 1;
    }

    int frame_count = 0;
    {
        std::istringstream stream(argv[1]);
        stream >> frame_count;
    }

    MeasurementOptions options;
    if (argc >= 3) {
        std::istringstream stream(argv[2]);
        stream >> options.stability_reads;
    }
    if (argc >= 4) {
        std::istringstream stream(argv[3]);
        stream >> options.stability_tolerance;
    }
    if (argc >= 5) {
        std::istringstream stream(argv[4]);
        stream >> options.channel6_reads;
    }

    Plant plant;
    plant_init(plant);

    const MeasurementResult result = run_measurements(frame_count, plant, options);
    if (!result.success) {
        cerr << result.error_message << '\n';
        return 2;
    }

    for (size_t i = 0; i < result.frames.size(); ++i) {
        const MeasurementFrame& frame = result.frames[i];
        cout
            << "FRAME\t"
            << frame.number << '\t'
            << frame.channel_1 << '\t'
            << frame.channel_2 << '\t'
            << frame.channel_3 << '\t'
            << frame.channel_4 << '\t'
            << frame.channel_5 << '\t'
            << frame.channel_6_avg << '\t'
            << frame.channel_6_disp << '\t'
            << frame.channel_19 << '\t'
            << frame.channel_49 << '\t'
            << frame.channel_69_func << '\n';
    }

    cout << "END_TIME_MSK\t" << result.end_time_msk << '\n';
    return 0;
}
