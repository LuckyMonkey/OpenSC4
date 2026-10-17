// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Small process boundary for the external OpenGlassBox library. The JSON
// protocol lives in openglassbox_sidecar.py; this helper deliberately uses a
// tiny line protocol so the bridge has no third-party JSON dependency.

#include "OpenGlassBox/Path.hpp"
#include "OpenGlassBox/Simulation.hpp"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>

#ifndef OPENSC4_OGB_COMMIT
#define OPENSC4_OGB_COMMIT "unknown"
#endif

namespace
{

class Helper
{
public:
    Helper()
        : m_roadType("Road", 0xAAAAAA),
          m_segmentType("Dirt", 0xAAAAAA)
    {
        reset();
    }

    void reset()
    {
        m_simulation = std::make_unique<ogb::Simulation>();
        m_simulation->setPaused(false);
        m_city = &m_simulation->addCity("OpenSC4", ogb::Vector3f(0.0f, 0.0f, 0.0f), 32u, 32u);
    }

    bool addRoad(float x1, float y1, float x2, float y2)
    {
        if (m_city == nullptr)
            return false;
        ogb::Path* road = nullptr;
        auto const& paths = m_city->getPaths();
        auto found = paths.find("Road");
        if (found == paths.end())
            road = &m_city->addPath(m_roadType);
        else
            road = found->second.get();
        ogb::Node& from = road->addNode(ogb::Vector3f(x1, y1, 0.0f));
        ogb::Node& to = road->addNode(ogb::Vector3f(x2, y2, 0.0f));
        road->addSegment(m_segmentType, from, to);
        return true;
    }

    bool advance(float seconds)
    {
        if (seconds < 0.0f || !std::isfinite(seconds))
            return false;
        constexpr float ticksPerSecond = 20.0f;
        double requested = std::round(static_cast<double>(seconds) * ticksPerSecond);
        if (requested < 0.0 || requested > 2000000.0)
            return false;
        for (std::uint64_t index = 0u; index < static_cast<std::uint64_t>(requested); ++index)
            m_simulation->stepOneTick();
        return true;
    }

    bool setTick(std::uint64_t tick)
    {
        if (m_simulation == nullptr)
            return false;
        m_simulation->setTicks(tick);
        return true;
    }

    std::string snapshot() const
    {
        std::size_t paths = 0u;
        std::size_t nodes = 0u;
        std::size_t segments = 0u;
        if (m_city != nullptr)
        {
            paths = m_city->getPaths().size();
            for (auto const& item : m_city->getPaths())
            {
                nodes += item.second->getNodeCount();
                segments += item.second->getSegments().size();
            }
        }
        auto const& clock = m_simulation->getClock();
        std::ostringstream result;
        result << "OK"
               << " commit=" << OPENSC4_OGB_COMMIT
               << " tick=" << clock.getTicks()
               << " day=" << clock.getDay()
               << " hour=" << clock.getHourOfDay()
               << " minute=" << clock.getMinuteOfHour()
               << " cities=" << m_simulation->getCities().size()
               << " paths=" << paths
               << " nodes=" << nodes
               << " segments=" << segments;
        return result.str();
    }

    std::string version() const
    {
        return std::string("OK commit=") + OPENSC4_OGB_COMMIT;
    }

    bool handle(std::string const& line, std::string& output)
    {
        std::istringstream input(line);
        std::string command;
        input >> command;
        if (command == "RESET")
        {
            reset();
            output = "OK";
            return true;
        }
        if (command == "VERSION")
        {
            output = version();
            return true;
        }
        if (command == "SNAPSHOT")
        {
            output = snapshot();
            return true;
        }
        if (command == "SET_TICK")
        {
            std::uint64_t tick = 0u;
            if (!(input >> tick) || !setTick(tick))
            {
                output = "ERR invalid_tick";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "ADVANCE")
        {
            float seconds = 0.0f;
            if (!(input >> seconds) || !advance(seconds))
            {
                output = "ERR invalid_seconds";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "ADD_ROAD")
        {
            float x1 = 0.0f;
            float y1 = 0.0f;
            float x2 = 0.0f;
            float y2 = 0.0f;
            if (!(input >> x1 >> y1 >> x2 >> y2) || !addRoad(x1, y1, x2, y2))
            {
                output = "ERR invalid_road";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "QUIT")
        {
            output = "OK";
            return false;
        }
        output = "ERR unknown_command";
        return true;
    }

private:
    // Recipes are kept outside Simulation so their addresses remain stable for
    // every Path and Segment owned by the current city.
    ogb::PathType m_roadType;
    ogb::SegmentType m_segmentType;
    std::unique_ptr<ogb::Simulation> m_simulation;
    ogb::City* m_city = nullptr;
};

} // namespace

int main()
{
    Helper helper;
    std::string line;
    while (std::getline(std::cin, line))
    {
        std::string output;
        bool keepRunning = helper.handle(line, output);
        std::cout << output << '\n' << std::flush;
        if (!keepRunning)
            break;
    }
    return 0;
}
